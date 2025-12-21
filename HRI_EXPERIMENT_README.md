# HRI Co-Manipulation Experiment GUI

## Overview

This is a professional 2D top-down graphical user interface for human-robot co-manipulation experiments. The system supports randomized and manual experiment execution with 18 scenarios per participant pair.

## Features

### ✅ Core Requirements Met

- **2D Top-Down Workspace Visualization**
  - Fixed workspace: 0.8m (width) × 1.5m (height)
  - Normalized coordinate system with origin at start position
  - Real-time visual feedback

- **Three Target Zones**
  - Target 1: (0.3, 1.0, 0)
  - Target 2: (0.0, 1.4, 0)
  - Target 3: (-0.3, 1.2, 0)
  - Active target highlighting with glow effect
  - Automatic target switching for "Change" scenarios

- **Dynamic Obstacle Display**
  - Size: 0.16m × 0.10m × 0.23m
  - Position: (0.0, 0.5, 0)
  - Visible only in Obstacle and Change+Obstacle modes

- **Start Zone**
  - Pink when idle/waiting
  - Blue when trial is running

### 🎲 Randomization System

**Random Mode = ON**
- Automatically randomizes mode order
- Randomizes scenario order within each mode
- Executes all scenarios of one mode before switching
- Manual selection disabled

**Random Mode = OFF**
- Full manual control
- Select any mode and scenario
- Useful for re-running failed trials
- Useful for re-collecting specific trajectories

### 🎯 Experiment Modes

1. **Free** (Scenarios 1-6)
   - No obstacles
   - Single target per scenario

2. **Obstacle** (Scenarios 7-12)
   - Static obstacle present
   - Single target per scenario

3. **Change** (Scenarios 13-15)
   - No obstacles
   - Target changes mid-trial at t_change

4. **Change + Obstacle** (Scenarios 16-18)
   - Obstacle present
   - Target changes mid-trial at t_change

### 📊 Scenario Mapping (Fixed)

| Scenario ID | Mode | Initial Target | Final Target |
|-------------|------|----------------|--------------|
| 1-6 | Free | 1,2,3,1,2,3 | 1,2,3,1,2,3 |
| 7-12 | Obstacle | 1,2,3,1,2,3 | 1,2,3,1,2,3 |
| 13 | Change | 1 | 2 |
| 14 | Change | 2 | 3 |
| 15 | Change | 3 | 1 |
| 16 | Change+Obstacle | 1 | 2 |
| 17 | Change+Obstacle | 2 | 3 |
| 18 | Change+Obstacle | 3 | 1 |

## Installation

### Requirements

```bash
Python 3.7+
tkinter (usually included with Python)
```

### Running the Application

```bash
python hri_experiment_gui.py
```

## Usage Guide

### Starting an Experiment

1. **Set Pair ID**: Enter the participant pair number (1-100)

2. **Choose Mode**:
   - **Random ON**: Automatic randomization (recommended for experiments)
   - **Random OFF**: Manual selection (for re-runs)

3. **Set t_change**: 
   - Only for Change scenarios
   - Default: 3.0 seconds
   - Adjustable range: 0.5 - 10.0 seconds

4. **Click Start**: 
   - In Random mode: automatically loads first scenario
   - In Manual mode: select mode and scenario first

### During a Trial

- **Start zone** turns **blue** when trial begins
- **Active target** glows bright yellow
- For **Change scenarios**: target switches at t_change
- **Obstacle** appears only in relevant modes

### Advancing Through Scenarios

- Click **Next Scenario** after completing a trial
- Progress shown as "X / 18"
- System prevents advancing before trial starts

### Resetting

- Click **Reset Experiment** to return to idle state
- Clears all progress and scenario queue

## Architecture

### State Machine

```
IDLE → READY → RUNNING → WAITING_NEXT → (next scenario or FINISHED)
```

- **IDLE**: No scenario selected
- **READY**: Scenario loaded, waiting to start
- **RUNNING**: Trial in progress
- **WAITING_NEXT**: Trial complete, waiting for next
- **FINISHED**: All 18 scenarios complete

### Key Components

1. **ExperimentManager**
   - Manages state machine
   - Handles scenario sequencing
   - Controls randomization
   - Tracks progress

2. **WorkspaceCanvas**
   - 2D visualization
   - World-to-canvas coordinate conversion
   - Dynamic element rendering
   - Visual state updates

3. **ControlPanel**
   - Experimenter interface
   - Parameter configuration
   - Manual/automatic control
   - Real-time feedback

### Separation of Concerns

✅ **Experiment Logic** (ExperimentManager)
- State management
- Scenario selection
- Timing control

✅ **Visualization** (WorkspaceCanvas)
- Rendering
- Coordinate transformation
- Visual feedback

✅ **User Interface** (ControlPanel)
- Input handling
- Control flow
- Status display

## Design Philosophy (HRI-Specific)

### Minimalistic Interface
- Clean 2D top-down view
- No textual instructions during trials
- Focus on spatial information only

### Information Hiding
The GUI **never displays**:
- Robot goals or intentions
- Force/torque data
- Internal states
- Predictive information

### Visual Clarity
- High contrast colors
- Clear target highlighting
- Smooth state transitions
- Intuitive color coding

## Extension Points

### Data Logging

Add logging in `ExperimentManager`:

```python
def begin_trial(self):
    if self.state == ExperimentState.READY:
        self.state = ExperimentState.RUNNING
        self.trial_start_time = datetime.now().timestamp()
        
        # ADD LOGGING HERE
        self.log_trial_start()
        
        return True
    return False

def log_trial_start(self):
    """Log trial start event"""
    log_data = {
        'timestamp': self.trial_start_time,
        'pair_id': self.current_pair_id,
        'scenario_id': self.current_scenario.scenario_id,
        'mode': self.current_scenario.modus.value,
        'initial_target': self.current_scenario.initial_target,
        'final_target': self.current_scenario.final_target,
    }
    # Write to file or database
```

### Trajectory Visualization

Add to `WorkspaceCanvas`:

```python
def __init__(self, parent, experiment_manager, **kwargs):
    super().__init__(parent, **kwargs)
    # ... existing code ...
    self.trajectory_points = []

def draw_trajectory(self, points):
    """Draw trajectory path"""
    if len(points) < 2:
        return
    
    for i in range(len(points) - 1):
        x1, y1 = self.world_to_canvas(points[i][0], points[i][1])
        x2, y2 = self.world_to_canvas(points[i+1][0], points[i+1][1])
        self.create_line(x1, y1, x2, y2, fill="#00FF00", width=2, tags="trajectory")
```

### Real-time Robot Position

```python
def update_robot_position(self, x, y):
    """Update robot position marker"""
    cx, cy = self.world_to_canvas(x, y)
    
    # Remove old marker
    self.delete("robot")
    
    # Draw new marker
    self.create_oval(
        cx - 10, cy - 10, cx + 10, cy + 10,
        fill="#00FF00", outline="#FFFFFF", width=2,
        tags="robot"
    )
```

## Color Scheme

| Element | State | Color |
|---------|-------|-------|
| Start Zone | Idle | Pink (#FF69B4) |
| Start Zone | Running | Blue (#4A90E2) |
| Active Target | - | Bright Yellow (#FFD700) |
| Inactive Target | - | Dim Yellow (#665500) |
| Obstacle | - | Dark Red (#8B0000) |
| Workspace | Background | Dark Gray (#1a1a1a) |

## Troubleshooting

### GUI doesn't start
- Ensure Python 3.7+ is installed
- Check that tkinter is available: `python -m tkinter`

### Scenarios not randomizing
- Verify "Random Scenarios" checkbox is checked
- Click "Reset Experiment" and try again

### t_change not editable
- Only enabled for Change and Change+Obstacle scenarios
- Select appropriate scenario first

### Manual mode not working
- Uncheck "Random Scenarios"
- Select mode from dropdown
- Select scenario from dropdown
- Click "Start"

## Future Enhancements

Potential additions:
- [ ] Real-time trajectory recording
- [ ] Data export (CSV, JSON)
- [ ] Performance metrics display
- [ ] Multi-session management
- [ ] Replay functionality
- [ ] Network communication for robot control
- [ ] Force/torque data collection (backend only)

## License

Developed for Human-Robot Interaction research.

## Contact

For questions or issues, please contact your research supervisor or lab administrator.
