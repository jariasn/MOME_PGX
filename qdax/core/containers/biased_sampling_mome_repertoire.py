"""This file contains the class to define the repertoire used to
store individuals in the Multi-Objective MAP-Elites algorithm as
well as several variants."""

from __future__ import annotations

from functools import partial
from typing import Any, Tuple, List

import flax
import jax
import jax.numpy as jnp
from jax.flatten_util import ravel_pytree

from qdax.core.containers.mapelites_repertoire import (
    get_cells_indices,
)
from qdax.core.containers.mome_repertoire import (
    MOMERepertoire,
)
from qdax.types import (
    Centroid,
    Descriptor,
    Fitness,
    Genotype,
    Mask,
    ParetoFront,
    RNGKey,
)
from qdax.utils.pareto_front import compute_masked_pareto_front


class BiasedSamplingMOMERepertoire(MOMERepertoire):
    """Class for the repertoire in Multi Objective Map Elites

    This class inherits from MAPElitesRepertoire. The stored data
    is the same: genotypes, fitnesses, descriptors, centroids.

    The shape of genotypes is (in the case where it's an array):
    (num_centroids, pareto_front_length, genotype_dim).
    When the genotypes is a PyTree, the two first dimensions are the same
    but the third will depend on the leafs.

    The shape of fitnesses is: (num_centroids, pareto_front_length, num_criteria)

    The shape of descriptors and centroids are:
    (num_centroids, num_descriptors, pareto_front_length).

    Inherited functions: save and load.
    """
    genotypes: Genotype
    fitnesses: Fitness
    descriptors: Descriptor
    centroids: Centroid
   
    @jax.jit
    def _sample_in_masked_pareto_front(
        self,
        pareto_front_genotypes: ParetoFront[Genotype],
        pareto_front_fitnesses: ParetoFront[Fitness],
        mask: Mask,
        random_key: RNGKey,
    ) -> Genotype:
        """Sample one single genotype in masked pareto front.

        Note: do not retrieve a random key because this function
        is to be vmapped. The public method that uses this function
        will return a random key

        Args:
            pareto_front_genotypes: the genotypes of a pareto front
            mask: a mask associated to the front
            random_key: a random key to handle stochastic operations

        Returns:
            A single genotype among the pareto front.
        """
        # mask: 1 if empty, 0 if not
        not_empty_mask = 1.0 - mask
        num_solutions = jnp.sum(not_empty_mask)

        num_objective = pareto_front_fitnesses.shape[1]

        def compute_equal_probabilities(
            mask,
            fitnesses,
        )-> jnp.array:

            equal_probs = (not_empty_mask) / jnp.sum(not_empty_mask)
            return equal_probs
        
        def compute_crowding_distances(
            mask,
            pareto_front_fitnesses,
        ) -> jnp.array:

            # mask over each objectice
            mask_dist = jnp.column_stack([mask] * pareto_front_fitnesses.shape[1])

            # calculate min and max of fitnesses, ignoring NaNs
            score_amplitude = jnp.nanmax(pareto_front_fitnesses*mask_dist, axis=0) - jnp.nanmin(pareto_front_fitnesses*mask_dist, axis=0)
            
            dist_fitnesses = (
                pareto_front_fitnesses + 3 * score_amplitude * jnp.ones_like(pareto_front_fitnesses) * mask_dist
            )

            sorted_index = jnp.argsort(dist_fitnesses, axis=0)
            srt_fitnesses = pareto_front_fitnesses[sorted_index, jnp.arange(num_objective)]

            # get the distances
            dists = jnp.row_stack(
                [srt_fitnesses, jnp.full(num_objective, jnp.inf)]
            ) - jnp.row_stack([jnp.full(num_objective, -jnp.inf), srt_fitnesses])

            # Prepare the distance to last and next vectors
            dist_to_last = dists[:-1] / score_amplitude
            dist_to_next = dists[1:] / score_amplitude

            # Replace end point distances of inf, with the distance of NN from other side
            dist_to_last_with_ends = jnp.where(dist_to_last == jnp.inf, dist_to_next, dist_to_last)
            dist_to_next_with_ends = jnp.where(dist_to_next == jnp.inf, dist_to_last, dist_to_next)

            # Sum up the distances and reorder
            j = jnp.argsort(sorted_index, axis=0)
            crowding_distances = (
                jnp.sum(
                    (
                        dist_to_last_with_ends[j, jnp.arange(num_objective)]
                        + dist_to_next_with_ends[j, jnp.arange(num_objective)]
                    ),
                    axis=1,
                )
                / num_objective
            )
            # Set empty pf cells probability of selection to 0
            crowding_distances = jnp.where(jnp.isnan(crowding_distances), 0, crowding_distances)

            # Replace crowding distance of inf 
            normalised_crowding_distances = crowding_distances/jnp.nansum(crowding_distances)

            return normalised_crowding_distances
        
        selection_probs = jax.lax.cond(
            num_solutions <= 2, 
            compute_equal_probabilities,
            compute_crowding_distances, 
            *(not_empty_mask, pareto_front_fitnesses)
        )

        genotype_sample = jax.tree_util.tree_map(
            lambda x: jax.random.choice(random_key, x, shape=(1,), p=selection_probs),
            pareto_front_genotypes,
        )

        return genotype_sample

    @partial(jax.jit, static_argnames=("num_samples",))
    def sample(self, random_key: RNGKey, num_samples: int) -> Tuple[Genotype, RNGKey]:
        """Sample elements in the repertoire.

        This method sample a non-empty pareto front, and then sample
        genotypes from this pareto front.

        Args:
            random_key: a random key to handle stochasticity.
            num_samples: number of samples to retrieve from the repertoire.

        Returns:
            A sample of genotypes and a new random key.
        """

        # create sampling probability for the cells
        repertoire_empty = jnp.any(self.fitnesses == -jnp.inf, axis=-1)
        occupied_cells = jnp.any(~repertoire_empty, axis=-1)

        p = occupied_cells / jnp.sum(occupied_cells)

        # possible indices - num cells
        indices = jnp.arange(start=0, stop=repertoire_empty.shape[0])

        # choose idx - among indices of cells that are not empty
        random_key, subkey = jax.random.split(random_key)
        cells_idx = jax.random.choice(subkey, indices, shape=(num_samples,), p=p)

        # get genotypes (front) from the chosen indices
        pareto_front_genotypes = jax.tree_util.tree_map(
            lambda x: x[cells_idx], self.genotypes
        )

        # get fitnesses from the chosen indices
        pareto_front_fitnesses = jax.tree_util.tree_map(
            lambda x: x[cells_idx], self.fitnesses
        )
        # prepare second sampling function
        sample_in_fronts = jax.vmap(self._sample_in_masked_pareto_front)

        # sample genotypes from the pareto front
        random_key, subkey = jax.random.split(random_key)
        subkeys = jax.random.split(subkey, num=num_samples)
        sampled_genotypes = sample_in_fronts(  # type: ignore
            pareto_front_genotypes=pareto_front_genotypes,
            pareto_front_fitnesses=pareto_front_fitnesses,
            mask=repertoire_empty[cells_idx],
            random_key=subkeys,
        )

        # remove the dim coming from pareto front
        sampled_genotypes = jax.tree_util.tree_map(
            lambda x: x.squeeze(axis=1), sampled_genotypes
        )

        return sampled_genotypes, random_key

    @jax.jit
    def _update_masked_pareto_front(
        self,
        pareto_front_fitnesses: ParetoFront[Fitness],
        pareto_front_genotypes: ParetoFront[Genotype],
        pareto_front_descriptors: ParetoFront[Descriptor],
        mask: Mask,
        new_batch_of_fitnesses: Fitness,
        new_batch_of_genotypes: Genotype,
        new_batch_of_descriptors: Descriptor,
        new_mask: Mask,
    ) -> Tuple[
        ParetoFront[Fitness], ParetoFront[Genotype], ParetoFront[Descriptor], Mask
    ]:
        """Takes a fixed size pareto front, its mask and new points to add.
        Returns updated front and mask.

        Args:
            pareto_front_fitnesses: fitness of the pareto front
            pareto_front_genotypes: corresponding genotypes
            pareto_front_descriptors: corresponding descriptors
            mask: mask of the front, to hide void parts
            new_batch_of_fitnesses: new batch of fitness that is considered
                to be added to the pareto front
            new_batch_of_genotypes: corresponding genotypes
            new_batch_of_descriptors: corresponding descriptors
            new_mask: corresponding mask (no one is masked)

        Returns:
            The updated pareto front.
        """
        # mask: 1 if fitness  is -inf, 0 otherwise
        # get dimensions
        batch_size = new_batch_of_fitnesses.shape[0]
        num_criteria = new_batch_of_fitnesses.shape[1]

        pareto_front_len = pareto_front_fitnesses.shape[0]  # type: ignore
        descriptors_dim = new_batch_of_descriptors.shape[1]

        # gather all data
        cat_mask = jnp.concatenate([mask, new_mask], axis=-1)
        cat_fitnesses = jnp.concatenate(
            [pareto_front_fitnesses, new_batch_of_fitnesses], axis=0
        )
        cat_genotypes = jax.tree_util.tree_map(
            lambda x, y: jnp.concatenate([x, y], axis=0),
            pareto_front_genotypes,
            new_batch_of_genotypes,
        )
        cat_descriptors = jnp.concatenate(
            [pareto_front_descriptors, new_batch_of_descriptors], axis=0
        )

        # get new front
        cat_bool_front = compute_masked_pareto_front(
            batch_of_criteria=cat_fitnesses, mask=cat_mask
        )
        # get corresponding indices
        # have to add 50 to distinguish whether index 0 is part of front or not
        indices = (
            jnp.arange(start=0, stop=pareto_front_len + batch_size) * cat_bool_front
        )
        indices = indices + ~cat_bool_front * (batch_size + pareto_front_len - 1)
        indices = jnp.sort(indices)

        # get fitnesses, genotypes and descriptors of front (with non-front elements all equal to final element)
        all_front_fitnesses = jnp.take(cat_fitnesses, indices, axis=0)
        all_front_genotypes = jax.tree_util.tree_map(
            lambda x: jnp.take(x, indices, axis=0), cat_genotypes
        )
        all_front_descriptors = jnp.take(cat_descriptors, indices, axis=0)

        # compute new mask (which is to be used on all_front_genotypes etc)
        num_front_elements = jnp.sum(cat_bool_front)
        new_mask_indices = jnp.arange(start=0, stop=batch_size + pareto_front_len)
        new_mask_indices = (num_front_elements - new_mask_indices) > 0
        new_front_mask = jnp.where(
            new_mask_indices,
            jnp.ones(shape=batch_size + pareto_front_len, dtype=bool),
            jnp.zeros(shape=batch_size + pareto_front_len, dtype=bool),
        )

        # get fitnesses, descriptors and genotypes on front, with non-front values set to 0/-inf 
        fitness_mask = jnp.repeat(
            jnp.expand_dims(new_front_mask, axis=-1), num_criteria, axis=-1
        )
        
        # set non-front fitnesses = -inf
        all_front_fitnesses = all_front_fitnesses * fitness_mask  - jnp.inf * jnp.expand_dims(~new_front_mask, axis=-1) 
        all_front_fitnesses = jnp.where(jnp.isnan(all_front_fitnesses), -jnp.inf*jnp.ones_like(all_front_fitnesses), all_front_fitnesses)

        all_front_genotypes = jax.tree_util.tree_map(
            lambda x: x * new_mask_indices[0], all_front_genotypes
        )
        descriptors_mask = jnp.repeat(
            jnp.expand_dims(new_front_mask, axis=-1), descriptors_dim, axis=-1
        )
        all_front_descriptors = all_front_descriptors * descriptors_mask
        
        # reduce pareto front length to max length by removinf solutions with smallest crowding distnace
        empty_mask = jnp.any(all_front_fitnesses == -jnp.inf, axis=-1)

        # create mask over objective dims
        mask_dist = jnp.column_stack([~empty_mask] * all_front_fitnesses.shape[1])

        # calculate min and max of fitnesses, ignoring NaNs
        score_amplitude = jnp.nanmax(all_front_fitnesses*mask_dist, axis=0) - jnp.nanmin(all_front_fitnesses*mask_dist, axis=0)
        
        dist_fitnesses = (
            all_front_fitnesses + 3 * score_amplitude * jnp.ones_like(all_front_fitnesses) * mask_dist
        )

        sorted_index = jnp.argsort(dist_fitnesses, axis=0)
        srt_fitnesses = all_front_fitnesses[sorted_index, jnp.arange(num_criteria)]

        # get the distances
        dists = jnp.row_stack(
            [srt_fitnesses, jnp.full(num_criteria, jnp.inf)]
        ) - jnp.row_stack([jnp.full(num_criteria, -jnp.inf), srt_fitnesses])

        # Prepare the distance to last and next vectors
        dist_to_last = dists[:-1] / score_amplitude
        dist_to_next = dists[1:] / score_amplitude

        # Sum up the distances and reorder
        j = jnp.argsort(sorted_index, axis=0)
        crowding_distances = (
            jnp.sum(
                (
                    dist_to_last[j, jnp.arange(num_criteria)]
                    + dist_to_next[j, jnp.arange(num_criteria)]
                ),
                axis=1,
            )
            / num_criteria
        )

        # replace empty distances with -inf
        crowding_distances = jnp.where(jnp.isnan(crowding_distances), -jnp.inf, crowding_distances)

        # Get indices of smallest crowding distances
        sorted_distances_index = jnp.argsort(crowding_distances)

        # keep solutions with largest crowding distances
        keep_indices = sorted_distances_index[-pareto_front_len:]

        # turn empty fitnesses back to zero 
        all_front_fitnesses = jnp.where(all_front_fitnesses == -jnp.inf*jnp.ones_like(all_front_fitnesses), 
            jnp.zeros_like(all_front_fitnesses), 
            all_front_fitnesses)

        # get new pf with only 
        new_front_fitnesses = jnp.take(all_front_fitnesses, keep_indices, axis=0)
        new_front_genotypes = jax.tree_util.tree_map(
            lambda x: jnp.take(x, keep_indices, axis=0), all_front_genotypes
        )
        new_front_descriptors = jnp.take(all_front_descriptors, keep_indices, axis=0)
        new_mask = jnp.take(empty_mask, keep_indices)

        # Gather container addition metrics
        added_bool = jnp.any(new_front_fitnesses == new_batch_of_fitnesses) # check if new fitness is in pf
        removed_count = jnp.sum(~mask)- jnp.sum(~new_mask) - added_bool.astype(int) # Count how many were on front before

        return new_front_fitnesses, new_front_genotypes, new_front_descriptors, new_mask, added_bool, removed_count


    @classmethod
    def init(  # type: ignore
        cls,
        genotypes: Genotype,
        fitnesses: Fitness,
        descriptors: Descriptor,
        centroids: Centroid,
        pareto_front_max_length: int,
    ) -> Tuple[MOMERepertoire, List]:
        """
        Initialize a Multi Objective Map-Elites repertoire with an initial population
        of genotypes. Requires the definition of centroids that can be computed with
        any method such as CVT or Euclidean mapping.

        Note: this function has been kept outside of the object MapElites, so it can
        be called easily called from other modules.

        Args:
            genotypes: initial genotypes, pytree in which leaves
                have shape (batch_size, num_features)
            fitnesses: fitness of the initial genotypes of shape:
                (batch_size, num_criteria)
            descriptors: descriptors of the initial genotypes
                of shape (batch_size, num_descriptors)
            centroids: tesselation centroids of shape (batch_size, num_descriptors)
            pareto_front_max_length: maximum size of the pareto fronts

        Returns:
            An initialized MAP-Elite repertoire
        """

        # get dimensions
        num_criteria = fitnesses.shape[1]
        num_descriptors = descriptors.shape[1]
        num_centroids = centroids.shape[0]

        # create default values
        default_fitnesses = -jnp.inf * jnp.ones(
            shape=(num_centroids, pareto_front_max_length, num_criteria)
        )
        default_genotypes = jax.tree_util.tree_map(
            lambda x: jnp.zeros(
                shape=(
                    num_centroids,
                    pareto_front_max_length,
                )
                + x.shape[1:] # Use [1:] as first dimension is batch size (so ignore this)
            ),
            genotypes,
        )
        default_descriptors = jnp.zeros(
            shape=(num_centroids, pareto_front_max_length, num_descriptors)
        )

        # create repertoire with default values
        repertoire = BiasedSamplingMOMERepertoire(  # type: ignore
            genotypes=default_genotypes,
            fitnesses=default_fitnesses,
            descriptors=default_descriptors,
            centroids=centroids,
        )

        # add first batch of individuals in the repertoire
        new_repertoire, container_addition_metrics = repertoire.add(genotypes, descriptors, fitnesses)

        return new_repertoire, container_addition_metrics  # type: ignore

