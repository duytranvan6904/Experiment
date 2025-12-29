import pandas as pd
import numpy as np
import os

def create_train_test_split():
    input_file = 'experiment_trajectories.csv'
    train_output = 'train_trajectories.csv'
    test_output = 'test_trajectories.csv'
    
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    print(f"Loading {input_file}...")
    df = pd.read_csv(input_file)
    
    # 1. Identify Trajectories
    # Assumption: A new trajectory starts when Timestamp is 0.
    # We assign a unique ID to each block starting with 0.
    # Note: This assumes the file is ordered such that trajectories are contiguous blocks.
    df['TrajectoryId'] = (df['Timestamp'] == 0).cumsum()
    
    print(f"Total rows: {len(df)}")
    unique_trajs = df['TrajectoryId'].unique()
    print(f"Total trajectories identified: {len(unique_trajs)}")
    
    # 2. Analyze Scenarios
    # Get the ScenarioId for each Trajectory (take first row's ScenarioId)
    traj_metadata = df.groupby('TrajectoryId')['ScenarioId'].first().reset_index()
    
    scenario_counts = traj_metadata['ScenarioId'].value_counts()
    print("\nTrajectories per Scenario:")
    print(scenario_counts)
    
    # Filter scenarios that have at least 2 trajectories
    valid_scenarios = scenario_counts[scenario_counts >= 2].index.tolist()
    print(f"\nScenarios with >= 2 trajectories: {len(valid_scenarios)}")
    
    required_scenarios = 18
    trajs_per_scenario = 3
    
    if len(valid_scenarios) < required_scenarios:
        print(f"WARNING: Found only {len(valid_scenarios)} valid scenarios. "
              f"Cannot satisfy requirement of {required_scenarios} distinct scenarios.")
        # Fallback: Take all valid ones
        selected_scenarios = valid_scenarios
    else:
        # Randomly select 18 scenarios
        selected_scenarios = np.random.choice(valid_scenarios, required_scenarios, replace=False)
        
    print(f"Selected {len(selected_scenarios)} scenarios for the Test Set.")
    
    # 3. Select Trajectories for Test Set
    test_traj_ids = []
    for sc_id in selected_scenarios:
        # Get all trajectories for this scenario
        trajs_in_scenario = traj_metadata[traj_metadata['ScenarioId'] == sc_id]['TrajectoryId'].values
        # Randomly sample 3
        selected = np.random.choice(trajs_in_scenario, trajs_per_scenario, replace=False)
        test_traj_ids.extend(selected)
        
    print(f"Total trajectories selected for Test Set: {len(test_traj_ids)}")
    
    # 4. Separate Identifiers
    all_traj_ids = set(traj_metadata['TrajectoryId'].values)
    test_traj_ids_set = set(test_traj_ids)
    train_traj_ids_set = all_traj_ids - test_traj_ids_set
    
    train_traj_ids_list = list(train_traj_ids_set)
    test_traj_ids_list = list(test_traj_ids_set)
    
    # 5. Shuffle the order of trajectories
    np.random.shuffle(train_traj_ids_list)
    np.random.shuffle(test_traj_ids_list)
    
    print("Shuffled trajectory order for output files.")
    
    # 6. Construct Output DataFrames
    # Helper to build dataframe in specific trajectory order
    def build_ordered_df(source_df, id_list):
        if not id_list:
            return pd.DataFrame(columns=source_df.columns)
            
        # Filter rows
        subset = source_df[source_df['TrajectoryId'].isin(id_list)].copy()
        
        # Enforce order using Categorical
        # This ensures that when we sort, it follows the order of id_list
        subset['TrajectoryId'] = subset['TrajectoryId'].astype(
            pd.CategoricalDtype(categories=id_list, ordered=True)
        )
        # Sort by TrajectoryId (shuffled order), then Timestamp (preserve time order)
        return subset.sort_values(['TrajectoryId', 'Timestamp'])

    train_df = build_ordered_df(df, train_traj_ids_list)
    test_df = build_ordered_df(df, test_traj_ids_list)
    
    # 7. Clean up (Remove helper column)
    # We want to keep original columns.
    original_cols = ['Timestamp', 'X', 'Y', 'Z', 'Joint', 'ScenarioId']
    # Ensure they exist (Joint/ScenarioId might be varying but we read them)
    train_final = train_df[original_cols]
    test_final = test_df[original_cols]
    
    # 8. Save
    print(f"Saving {train_output} ({len(train_final)} rows)...")
    train_final.to_csv(train_output, index=False)
    
    print(f"Saving {test_output} ({len(test_final)} rows)...")
    test_final.to_csv(test_output, index=False)
    print("Process complete.")

if __name__ == "__main__":
    create_train_test_split()
