"""
Test coordinate system for HRI GUI
"""

# Canvas settings
canvas_width = 600
canvas_height = 950
margin_bottom = 80
margin_top = 20
draw_height = canvas_height - margin_bottom - margin_top

# Workspace dimensions
WORKSPACE_WIDTH = 0.8
WORKSPACE_HEIGHT = 1.5

# Scaling
scale_x = (canvas_width - 40) / WORKSPACE_WIDTH
scale_y = draw_height / WORKSPACE_HEIGHT

def world_to_canvas(x, y):
    """Convert world coordinates to canvas coordinates"""
    canvas_x = canvas_width / 2 + x * scale_x
    canvas_y = (canvas_height - margin_bottom) - y * scale_y
    return int(canvas_x), int(canvas_y)

# Test positions
print("=" * 60)
print("COORDINATE SYSTEM TEST")
print("=" * 60)
print(f"Canvas size: {canvas_width} x {canvas_height}")
print(f"Margins: top={margin_top}, bottom={margin_bottom}")
print(f"Drawing area: {canvas_width} x {draw_height}")
print(f"Scale: x={scale_x:.2f} px/m, y={scale_y:.2f} px/m")
print("=" * 60)

# Start position
start_pos = (0.0, 0.0, 0.0)
cx, cy = world_to_canvas(start_pos[0], start_pos[1])
print(f"\nSTART POSITION: {start_pos}")
print(f"  Canvas coords: ({cx}, {cy})")
print(f"  Within bounds: {0 <= cx <= canvas_width and 0 <= cy <= canvas_height}")

# Target positions
TARGET_POSITIONS = {
    3: (0.3, 1.0, 0.0),
    2: (0.0, 1.4, 0.0),
    1: (-0.3, 1.2, 0.0)
}

print("\nTARGET POSITIONS:")
for tid, pos in TARGET_POSITIONS.items():
    cx, cy = world_to_canvas(pos[0], pos[1])
    in_bounds = 0 <= cx <= canvas_width and 0 <= cy <= canvas_height
    print(f"  Target {tid}: {pos}")
    print(f"    Canvas coords: ({cx}, {cy})")
    print(f"    Within bounds: {in_bounds}")

# Obstacle
obstacle_center = (0.0, 0.5, 0.0)
cx, cy = world_to_canvas(obstacle_center[0], obstacle_center[1])
print(f"\nOBSTACLE CENTER: {obstacle_center}")
print(f"  Canvas coords: ({cx}, {cy})")
print(f"  Within bounds: {0 <= cx <= canvas_width and 0 <= cy <= canvas_height}")

print("\n" + "=" * 60)
print("All elements should be within bounds!")
print("=" * 60)
