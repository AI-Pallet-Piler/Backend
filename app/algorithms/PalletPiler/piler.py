from ortools.sat.python import cp_model
import json

class Item:
    def __init__(self, id, name, w, d, h, weight):
        self.id = id
        self.name = name
        self.w = w
        self.d = d
        self.h = h
        self.weight = weight 
        # Calculate area for "Biggest on Bottom" logic (Width x Depth)
        self.area = w * d 
        self.volume = w * d * h

def solve_single_pallet(items, pallet_w, pallet_d, pallet_h):
    """
    Attempts to pack a list of items into ONE pallet.
    OPTIMIZED FOR DENSITY: Prioritizes packing volume, then minimizing total height.
    """
    model = cp_model.CpModel()

    # --- 1. Variables ---
    is_packed = {}
    x = {}
    y = {}
    z = {}
    
    # Variable to track the highest point used in the pallet
    # Minimizing this forces the pallet to be "flat" and dense.
    max_z = model.NewIntVar(0, pallet_h, 'max_z')

    for i, item in enumerate(items):
        is_packed[i] = model.NewBoolVar(f'is_packed_{i}')
        x[i] = model.NewIntVar(0, pallet_w, f'x_{i}')
        y[i] = model.NewIntVar(0, pallet_d, f'y_{i}')
        z[i] = model.NewIntVar(0, pallet_h, f'z_{i}')

    # --- 2. Constraints ---

    # A. Boundary Constraints
    for i, item in enumerate(items):
        model.Add(x[i] + item.w <= pallet_w).OnlyEnforceIf(is_packed[i])
        model.Add(y[i] + item.d <= pallet_d).OnlyEnforceIf(is_packed[i])
        model.Add(z[i] + item.h <= pallet_h).OnlyEnforceIf(is_packed[i])
        
        # Link max_z to the top of every packed item
        # If item is packed, max_z must be >= z[i] + height
        model.Add(max_z >= z[i] + item.h).OnlyEnforceIf(is_packed[i])

    # B. Pairwise Non-Overlap & PHYSICS LOGIC
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            
            # Relative positions
            left = model.NewBoolVar(f'{i}_left_{j}')
            right = model.NewBoolVar(f'{i}_right_{j}')
            behind = model.NewBoolVar(f'{i}_behind_{j}')
            front = model.NewBoolVar(f'{i}_front_{j}')
            below = model.NewBoolVar(f'{i}_below_{j}')
            above = model.NewBoolVar(f'{i}_above_{j}')

            # Geometric definitions
            model.Add(x[i] + items[i].w <= x[j]).OnlyEnforceIf(left)
            model.Add(x[j] + items[j].w <= x[i]).OnlyEnforceIf(right)
            model.Add(y[i] + items[i].d <= y[j]).OnlyEnforceIf(behind)
            model.Add(y[j] + items[j].d <= y[i]).OnlyEnforceIf(front)
            model.Add(z[i] + items[i].h <= z[j]).OnlyEnforceIf(below)
            model.Add(z[j] + items[j].h <= z[i]).OnlyEnforceIf(above)

            # Non-overlap enforcement
            model.AddBoolOr([left, right, behind, front, below, above]).OnlyEnforceIf([is_packed[i], is_packed[j]])

            # --- PHYSICS CONSTRAINTS ---
            
            # Rule 1: HEAVIEST ON BOTTOM
            if items[i].weight > items[j].weight:
                model.Add(above == False)
            elif items[j].weight > items[i].weight:
                model.Add(below == False)

            # Rule 2: BIGGEST AREA ON BOTTOM (Stability)
            # Use 1.2 buffer to allow similar items to stack
            if items[i].area > items[j].area * 1.2:
                model.Add(above == False)
            elif items[j].area > items[i].area * 1.2:
                model.Add(below == False)

    # --- 3. DENSITY OBJECTIVE ---
    # We want to maximize a score calculated as:
    # (Volume Packed) - (Penalty for Height) - (Gravity)
    
    volume_score = 0
    gravity_score = 0
    
    for i, item in enumerate(items):
        # Large reward for packing an item
        volume_score += (is_packed[i] * item.volume)
        # Small penalty for Z position (pushes individual items down)
        gravity_score += z[i]
    
    # We prioritize Volume heavily (10000x), then penalize Max Height (1000x), then Gravity (1x)
    # This forces the solver to fill the layer completely before moving up.
    model.Maximize(
        (volume_score * 10000) - (max_z * 1000) - gravity_score
    )

    # --- 4. Solve ---
    solver = cp_model.CpSolver()
    # High density requires more computation time
    solver.parameters.max_time_in_seconds = 30.0 
    # Use all CPU cores to find the best fit
    solver.parameters.num_search_workers = 8 
    
    status = solver.Solve(model)

    # Processing results
    packed_items_data = []
    unpacked_indices = []
    
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for i, item in enumerate(items):
            if solver.BooleanValue(is_packed[i]):
                packed_items_data.append({
                    "id": item.id,
                    "name": item.name,
                    "x": solver.Value(x[i]),
                    "y": solver.Value(y[i]),
                    "z": solver.Value(z[i]),
                    "w": item.w, "h": item.h, "d": item.d, "weight": item.weight
                })
            else:
                unpacked_indices.append(i)
    else:
        unpacked_indices = list(range(len(items)))
    
    return packed_items_data, unpacked_indices


# --- MULTI-PALLET SOLVER LOOP ---
def solve_multiple_pallets(items, pallet_w, pallet_d, pallet_h):
    all_pallets = []
    
    # CRITICAL STEP FOR DENSITY:
    # Sort input items by Weight (desc) and Volume (desc).
    # It is mathematically much easier to pack big rocks first, then fill gaps with sand.
    items.sort(key=lambda x: (x.weight, x.volume), reverse=True)
    
    remaining_items = items.copy()
    pallet_number = 1
    
    print(f"Starting job with {len(items)} items...")

    while len(remaining_items) > 0:
        print(f"Calculating Pallet {pallet_number} (Input: {len(remaining_items)} items)...")
        
        packed, unpacked_indices = solve_single_pallet(remaining_items, pallet_w, pallet_d, pallet_h)
        
        if len(packed) == 0:
            print(f"⚠ CRITICAL: {len(remaining_items)} items are too large to fit in ANY empty pallet!")
            break
        
        all_pallets.append({
            "pallet_id": pallet_number,
            "items": packed
        })
        
        print(f"  ✓ Pallet {pallet_number}: Packed {len(packed)} items.")
        
        # Prepare next batch
        next_batch = [remaining_items[i] for i in unpacked_indices]
        remaining_items = next_batch
        
        pallet_number += 1
    
    return all_pallets

# --- TEST DATA ---
all_items = [
    # Heavy Anvil (Must be on bottom)
    Item("Anvil", "Heavy Anvil", 10, 10, 10, weight=50), 
    # Light Pillows (Must be on top/floor)
    Item("Pillows", "Light Box", 30, 30, 30, weight=5),
    
    # A mix of medium items to test density
    Item("Med1", "Normal Box", 20, 20, 20, weight=10),
    Item("Med2", "Normal Box", 20, 20, 20, weight=10),
    Item("Med3", "Normal Box", 20, 20, 20, weight=10),
    Item("Med4", "Normal Box", 20, 20, 20, weight=10),
    
    # Odd shapes
    Item("Tall", "Tall Item", 10, 10, 60, weight=15),
    Item("Flat", "Flat Item", 60, 60, 5, weight=20),
    
    # Large Heavy items (Should form the base)
    Item("Heavy1", "Heavy Base 1", 45, 45, 20, weight=98),
    Item("Heavy2", "Heavy Base 2", 45, 45, 20, weight=99),
    Item("Heavy3", "Heavy Base 3", 45, 45, 20, weight=101),
    Item("Heavy4", "Heavy Base 4", 45, 45, 20, weight=97),
]

# --- EXECUTION ---
print("=" * 60)
print("HIGH DENSITY BIN PACKING SOLVER")
print("=" * 60)

final_manifest = solve_multiple_pallets(all_items, 100, 100, 100)

print("\n" + "=" * 60)
print("FINAL RESULT (JSON):")
print("=" * 60)
print(json.dumps(final_manifest, indent=2))