from environment import Environment
from decision_makers import Agent, AllHorizontal, AllLocal, AllVertical,Random,SingleAgent,RoundRobin,RuleBased
from lr_schedulers import constant,Linear
import numpy as np
import argparse
import torch
import os
import json
import pickle 
def main():
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    parser = argparse.ArgumentParser()
    parser.add_argument('--log_folder', type=str, default='log_folder', help='Path to the log folder')
    parser.add_argument('--hyperparameters_file', type=str, default='hyperparameters/hyperparameters.json', help='Path to the hyperparameters file')
    parser.add_argument('--epochs', type=int, default=2, help='Device to use')
    parser.add_argument('--validate', type=bool, default=False, help='Device to use')
    args  = parser.parse_args()

    os.makedirs(args.log_folder, exist_ok=True)
    with open(args.hyperparameters_file) as f:
        hyperparameters = json.load(f)
            
    number_of_servers=  hyperparameters['number_of_servers']
    env = Environment(
        number_of_servers=hyperparameters['number_of_servers'],
        private_cpu_capacities=hyperparameters['private_cpu_capacities'],
        public_cpu_capacities=hyperparameters['public_cpu_capacities'],
        connection_matrix=hyperparameters['connection_matrix'],
        cloud_computational_capacity=hyperparameters['cloud_computational_capacity'],
        episode_time=hyperparameters['episode_time'],
        static_frequency=hyperparameters['static_frequency'],
        task_arrive_probabilities=hyperparameters['task_arrive_probabilities'],
        task_size_mins=hyperparameters['task_size_mins'],
        task_size_maxs=hyperparameters['task_size_maxs'],
        task_size_distributions=hyperparameters['task_size_distributions'],
        timeout_delay_mins=hyperparameters['timeout_delay_mins'],
        timeout_delay_maxs=hyperparameters['timeout_delay_maxs'],
        timeout_delay_distributions=hyperparameters['timeout_delay_distributions'],
        priotiry_mins=hyperparameters['priotiry_mins'],
        priotiry_maxs=hyperparameters['priotiry_maxs'],
        priotiry_distributions=hyperparameters['priotiry_distributions'],
        computational_density_mins=hyperparameters['computational_density_mins'],
        computational_density_maxs=hyperparameters['computational_density_maxs'],
        computational_density_distributions=hyperparameters['computational_density_distributions'],
        drop_penalty_mins=hyperparameters['drop_penalty_mins'],
        drop_penalty_maxs=hyperparameters['drop_penalty_maxs'],
        drop_penalty_distributions=hyperparameters['drop_penalty_distributions']
    )
    
    
    scheduler_file= args.log_folder+'/scheduler.pth'
    scheduler_choices ={
        'constant': constant,
        'Linear': Linear(start=hyperparameters['learning_rate'],
                        end=hyperparameters['learning_rate_end'],
                            number_of_epochs=hyperparameters['lr_scheduler_epochs'])
        }
    
    scheduler =scheduler_choices[hyperparameters['scheduler_choice']]
    
    
    with open(scheduler_file, 'wb') as f:
        pickle.dump(scheduler, f)
    
    decision_makers = []
    
    decision_makers_choice ={
        'drl': Agent,
        'all_horizontal': AllHorizontal,
        'all_local': AllLocal,
        'all_vertical': AllVertical,
        'random': Random,
        'round_robin':RoundRobin,
        'rule_based':RuleBased,
        "single":SingleAgent
    }
    chosen_descision_maker = decision_makers_choice[hyperparameters['decision_makers']]

    decision_makers = []
    
    
    for i in range(number_of_servers):
        state_dimensions,foreign_queues,number_of_actions = env.get_server_dimensions(i)      
        lstm_shape = foreign_queues 

        decision_maker_params ={'number_of_actions': number_of_actions} 
        
        if hyperparameters['decision_makers'] == 'drl':
            decision_maker_params = {
                'id': i,
                'state_dimensions': state_dimensions,
                'lstm_shape': lstm_shape,
                'number_of_actions': number_of_actions,
                'hidden_layers': hyperparameters['hidden_layers'],
                'lstm_layers': hyperparameters['lstm_layers'],
                'lstm_time_step': hyperparameters['lstm_time_step'],
                'dropout_rate': hyperparameters['dropout_rate'],
                'dueling': hyperparameters['dueling'],
                'epsilon': hyperparameters['epsilon'],
                'epsilon_decrement': hyperparameters['epsilon_decrement'],
                'epsilon_end': hyperparameters['epsilon_end'],
                'gamma': hyperparameters['gamma'],
                'learning_rate': hyperparameters['learning_rate'],
                'scheduler_file':scheduler_file,
                'loss_function': getattr(torch.nn, hyperparameters['loss_function']),
                'optimizer': getattr(torch.optim, hyperparameters['optimizer']),
                'checkpoint_folder': args.log_folder+ '/agent_'+str(i)+'.pth',
                'save_model_frequency': hyperparameters['save_model_frequency'],
                'update_weight_percentage': hyperparameters['update_weight_percentage'],
                'memory_size': hyperparameters['memory_size'],
                'batch_size': hyperparameters['batch_size'],
                'replace_target_iter': hyperparameters['replace_target_iter'],
                'device': device
            }
        
        if hyperparameters['decision_makers'] == 'rule_based':
            foreign_cpus = env.get_foreign_cpus(i)
            decision_maker_params = {
                'number_of_actions': number_of_actions,
                'local_cpu': hyperparameters['private_cpu_capacities'][i],
                'foreign_cpus':foreign_cpus
            }
        
    
        decision_maker = chosen_descision_maker(**decision_maker_params)
        decision_makers.append(decision_maker)
        
        
        
    for key in hyperparameters:
        if key != 'connection_matrix':
            print(key ," : ",hyperparameters[key])
    for epoch in range(args.epochs):
        accumulated_rewards = []
        observations,done, info = env.reset()
        local_observations,public_queues =observations
        while not done:
            actions = np.zeros(number_of_servers, dtype=int)
            for i in range(number_of_servers):
                actions[i] = decision_makers[i].choose_action(local_observations[i],public_queues[i])
            observations,rewards,done,info = env.step(actions)
            local_observations_,public_queues_ =observations
            if not args.validate:
                for i in range(number_of_servers):
                        decision_makers[i].store_transitions(state = local_observations[i],
                                                    lstm_state=public_queues[i],
                                                    action = actions[i],
                                                    reward= rewards[i],
                                                    new_state=local_observations_[i],
                                                    new_lstm_state=public_queues_[i],
                                                    done=done)
                        
            local_observations,public_queues  = local_observations_,public_queues_
            accumulated_rewards.append(sum(rewards))
        
        print(f'Epoch {epoch} Accumulated rewards: {sum(accumulated_rewards)/len(accumulated_rewards)}')
        if not args.validate:
            for decision_maker in decision_makers:
                decision_maker.learn() 
                decision_maker.reset_lstm_history()

                                
                    
if __name__ == "__main__":
    main()