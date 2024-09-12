from dataclasses import dataclass
from typing import Callable, Tuple

import flax.linen as nn

from qdax.core.emitters.bandit_multi_emitter import BanditMultiEmitter
from qdax.core.emitters.multi_emitter import MultiEmitter
from qdax.core.emitters.qpg_emitter import QualityPGConfig, QualityPGEmitter
from qdax.core.emitters.standard_emitters import MixingEmitter
from qdax.environments.base_wrappers import QDEnv
from qdax.types import Params, RNGKey


@dataclass
class BanditMOPGAConfig:
    """Configuration for PGAME Algorithm"""
    
    num_objective_functions: int = 1 
    total_batch_size: int = 256
    bandit_scaling_param: float = 0.5
    dynamic_window_size: int = 50
    num_critic_training_steps: int = 300
    num_pg_training_steps: int = 100

    # TD3 params
    replay_buffer_size: int = 1000000
    critic_hidden_layer_size: Tuple[int, ...] = (256, 256)
    critic_learning_rate: float = 3e-4
    greedy_learning_rate: float = 3e-4
    policy_learning_rate: float = 1e-3
    noise_clip: float = 0.5
    policy_noise: float = 0.2
    discount: float = 0.99
    reward_scaling: float = 1.0
    batch_size: int = 256
    soft_tau_update: float = 0.005
    policy_delay: int = 2



class BanditMOPGAEmitter(BanditMultiEmitter):
    def __init__(
        self,
        config: BanditMOPGAConfig,
        policy_network: nn.Module,
        env: QDEnv,
        variation_fn: Callable[[Params, Params, RNGKey], Tuple[Params, RNGKey]],
    ) -> None:

        self._config = config
        self._policy_network = policy_network
        self._env = env
        self._variation_fn = variation_fn

        emitters = []

        for objective_index in range(config.num_objective_functions):

            qpg_config = QualityPGConfig(
                num_objective_functions=config.num_objective_functions,
                objective_function_index=objective_index,
                env_batch_size=config.total_batch_size,
                num_critic_training_steps=config.num_critic_training_steps,
                num_pg_training_steps=config.num_pg_training_steps,
                replay_buffer_size=config.replay_buffer_size,
                critic_hidden_layer_size=config.critic_hidden_layer_size,
                critic_learning_rate=config.critic_learning_rate,
                actor_learning_rate=config.greedy_learning_rate,
                policy_learning_rate=config.policy_learning_rate,
                noise_clip=config.noise_clip,
                policy_noise=config.policy_noise,
                discount=config.discount,
                reward_scaling=config.reward_scaling,
                batch_size=config.batch_size,
                soft_tau_update=config.soft_tau_update,
                policy_delay=config.policy_delay,
            )

            # define the quality emitter
            q_emitter = QualityPGEmitter(
                config=qpg_config, policy_network=policy_network, env=env
            )

            emitters.append(q_emitter)

        # define the GA emitter
        ga_emitter = MixingEmitter(
            mutation_fn=lambda x, r: (x, r),
            variation_fn=variation_fn,
            variation_percentage=1.0,
            batch_size=config.total_batch_size,
        )

        emitters.append(ga_emitter)


        super().__init__(
            emitters=tuple(emitters), 
            total_batch_size=config.total_batch_size, 
            bandit_scaling_param=config.bandit_scaling_param,
            num_emitters=len(emitters),
            dynamic_window_size=config.dynamic_window_size,
        )


class BanditManyEmitters(BanditMultiEmitter):
    def __init__(
        self,
        config: BanditMOPGAConfig,
        policy_network: nn.Module,
        env: QDEnv,
        variation_fn: Callable[[Params, Params, RNGKey], Tuple[Params, RNGKey]],
    ) -> None:

        self._config = config
        self._policy_network = policy_network
        self._env = env
        self._variation_fn = variation_fn

        emitters = []

        for objective_index in range(config.num_objective_functions):

            qpg_config1 = QualityPGConfig(
                num_objective_functions=config.num_objective_functions,
                objective_function_index=objective_index,
                env_batch_size=config.total_batch_size,
                num_critic_training_steps=config.num_critic_training_steps,
                num_pg_training_steps=config.num_pg_training_steps,
                replay_buffer_size=config.replay_buffer_size,
                critic_hidden_layer_size=config.critic_hidden_layer_size,
                critic_learning_rate=config.critic_learning_rate,
                actor_learning_rate=config.greedy_learning_rate,
                policy_learning_rate=config.policy_learning_rate,
                noise_clip=config.noise_clip,
                policy_noise=config.policy_noise,
                discount=config.discount,
                reward_scaling=config.reward_scaling,
                batch_size=config.batch_size,
                soft_tau_update=config.soft_tau_update,
                policy_delay=config.policy_delay,
            )

            qpg_config2 = QualityPGConfig(
                num_objective_functions=config.num_objective_functions,
                objective_function_index=objective_index,
                env_batch_size=config.total_batch_size,
                num_critic_training_steps= 2 * config.num_critic_training_steps,
                num_pg_training_steps=config.num_pg_training_steps,
                replay_buffer_size=config.replay_buffer_size,
                critic_hidden_layer_size=config.critic_hidden_layer_size,
                critic_learning_rate=config.critic_learning_rate,
                actor_learning_rate=config.greedy_learning_rate,
                policy_learning_rate=config.policy_learning_rate,
                noise_clip=config.noise_clip,
                policy_noise=config.policy_noise,
                discount=config.discount,
                reward_scaling=config.reward_scaling,
                batch_size=config.batch_size,
                soft_tau_update=config.soft_tau_update,
                policy_delay=config.policy_delay,
            )

            qpg_config3 = QualityPGConfig(
                num_objective_functions=config.num_objective_functions,
                objective_function_index=objective_index,
                env_batch_size=config.total_batch_size,
                num_critic_training_steps= 5 * config.num_critic_training_steps,
                num_pg_training_steps=config.num_pg_training_steps,
                replay_buffer_size=config.replay_buffer_size,
                critic_hidden_layer_size=config.critic_hidden_layer_size,
                critic_learning_rate=config.critic_learning_rate,
                actor_learning_rate=config.greedy_learning_rate,
                policy_learning_rate=config.policy_learning_rate,
                noise_clip=config.noise_clip,
                policy_noise=config.policy_noise,
                discount=config.discount,
                reward_scaling=config.reward_scaling,
                batch_size=config.batch_size,
                soft_tau_update=config.soft_tau_update,
                policy_delay=config.policy_delay,
            )

            qpg_config4 = QualityPGConfig(
                num_objective_functions=config.num_objective_functions,
                objective_function_index=objective_index,
                env_batch_size=config.total_batch_size,
                num_critic_training_steps=config.num_critic_training_steps,
                num_pg_training_steps=0.5 * config.num_pg_training_steps,
                replay_buffer_size=config.replay_buffer_size,
                critic_hidden_layer_size=config.critic_hidden_layer_size,
                critic_learning_rate=config.critic_learning_rate,
                actor_learning_rate=config.greedy_learning_rate,
                policy_learning_rate=config.policy_learning_rate,
                noise_clip=config.noise_clip,
                policy_noise=config.policy_noise,
                discount=config.discount,
                reward_scaling=config.reward_scaling,
                batch_size=config.batch_size,
                soft_tau_update=config.soft_tau_update,
                policy_delay=config.policy_delay,
            )

            qpg_config5 = QualityPGConfig(
                num_objective_functions=config.num_objective_functions,
                objective_function_index=objective_index,
                env_batch_size=config.total_batch_size,
                num_critic_training_steps=config.num_critic_training_steps,
                num_pg_training_steps=2 * config.num_pg_training_steps,
                replay_buffer_size=config.replay_buffer_size,
                critic_hidden_layer_size=config.critic_hidden_layer_size,
                critic_learning_rate=config.critic_learning_rate,
                actor_learning_rate=config.greedy_learning_rate,
                policy_learning_rate=config.policy_learning_rate,
                noise_clip=config.noise_clip,
                policy_noise=config.policy_noise,
                discount=config.discount,
                reward_scaling=config.reward_scaling,
                batch_size=config.batch_size,
                soft_tau_update=config.soft_tau_update,
                policy_delay=config.policy_delay,
            )

            # define the quality emitter
            q_emitter1 = QualityPGEmitter(
                config=qpg_config1, policy_network=policy_network, env=env
            )
            
            q_emitter2 = QualityPGEmitter(
                config=qpg_config2, policy_network=policy_network, env=env
            )
            
            q_emitter3 = QualityPGEmitter(
                config=qpg_config3, policy_network=policy_network, env=env
            )
            
            q_emitter4 = QualityPGEmitter(
                config=qpg_config4, policy_network=policy_network, env=env
            )
            
            q_emitter5 = QualityPGEmitter(
                config=qpg_config5, policy_network=policy_network, env=env
            )

            emitters.append(q_emitter1)
            emitters.append(q_emitter2)
            emitters.append(q_emitter3)
            emitters.append(q_emitter4)
            emitters.append(q_emitter5)

        # define the GA emitter
        ga_emitter = MixingEmitter(
            mutation_fn=lambda x, r: (x, r),
            variation_fn=variation_fn,
            variation_percentage=1.0,
            batch_size=config.total_batch_size,
        )

        emitters.append(ga_emitter)


        super().__init__(
            emitters=tuple(emitters), 
            total_batch_size=config.total_batch_size, 
            bandit_scaling_param=config.bandit_scaling_param,
            num_emitters=len(emitters),
            dynamic_window_size=config.dynamic_window_size,
        )
