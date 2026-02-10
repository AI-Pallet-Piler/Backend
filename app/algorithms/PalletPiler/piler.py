from ortools.sat.python import cp_model
import json

# --- 1. DATA STRUCTURE ---
class Item:
    def __init__(self, id, name, w, d, h, weight):
        self.id = id
        self.name = name
        self.w = w
        self.d = d
        self.h = h
        self.weight = weight 
        # Area is used for stability checks
        self.area = w * d 
        self.volume = w * d * h

# --- 2. CORE SOLVER LOGIC ---
def solve_single_pallet(items, pallet_w, pallet_d, pallet_h):
    """
    Attempts to pack a list of items into ONE pallet.
    Features: Rotation, Density Optimization, and Smart Stability (Light items can overhang).
    """
    model = cp_model.CpModel()

    # --- Variables ---
    is_packed = {}
    x = {}
    y = {}
    z = {}
    rotation = {} # 0 = Original, 1 = Rotated 90 degrees
    
    # Variable to track the highest point used (for density optimization)
    max_z = model.NewIntVar(0, pallet_h, 'max_z')

    for i, item in enumerate(items):
        is_packed[i] = model.NewBoolVar(f'is_packed_{i}')
        x[i] = model.NewIntVar(0, pallet_w, f'x_{i}')
        y[i] = model.NewIntVar(0, pallet_d, f'y_{i}')
        z[i] = model.NewIntVar(0, pallet_h, f'z_{i}')
        rotation[i] = model.NewBoolVar(f'rot_{i}')

    # --- Constraints ---

    # A. Effective Dimensions & Boundaries
    # We create variables for the "current" Width and Depth based on rotation
    current_w = {}
    current_d = {}

    for i, item in enumerate(items):
        # Define dimension variables
        current_w[i] = model.NewIntVar(0, max(item.w, item.d), f'cw_{i}')
        current_d[i] = model.NewIntVar(0, max(item.w, item.d), f'cd_{i}')

        # Link rotation to dimensions
        # If rotation=0: w=item.w, d=item.d
        model.Add(current_w[i] == item.w).OnlyEnforceIf(rotation[i].Not())
        model.Add(current_d[i] == item.d).OnlyEnforceIf(rotation[i].Not())
        # If rotation=1: w=item.d, d=item.w
        model.Add(current_w[i] == item.d).OnlyEnforceIf(rotation[i])
        model.Add(current_d[i] == item.w).OnlyEnforceIf(rotation[i])

        # Boundary Constraints (Must fit inside pallet)
        model.Add(x[i] + current_w[i] <= pallet_w).OnlyEnforceIf(is_packed[i])
        model.Add(y[i] + current_d[i] <= pallet_d).OnlyEnforceIf(is_packed[i])
        model.Add(z[i] + item.h <= pallet_h).OnlyEnforceIf(is_packed[i])
        
        # Link max_z
        model.Add(max_z >= z[i] + item.h).OnlyEnforceIf(is_packed[i])

    # B. Pairwise Non-Overlap & Physics
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            
            # Relative positions
            left = model.NewBoolVar(f'{i}_left_{j}')
            right = model.NewBoolVar(f'{i}_right_{j}')
            behind = model.NewBoolVar(f'{i}_behind_{j}')
            front = model.NewBoolVar(f'{i}_front_{j}')
            below = model.NewBoolVar(f'{i}_below_{j}')
            above = model.NewBoolVar(f'{i}_above_{j}')

            # We use the calculated current_w/current_d variables for collision
            # To allow variable sizes in Add(), we map them to intermediate End variables
            x_end_i = model.NewIntVar(0, pallet_w, f'xe_{i}')
            y_end_i = model.NewIntVar(0, pallet_d, f'ye_{i}')
            x_end_j = model.NewIntVar(0, pallet_w, f'xe_{j}')
            y_end_j = model.NewIntVar(0, pallet_d, f'ye_{j}')

            model.Add(x_end_i == x[i] + current_w[i])
            model.Add(y_end_i == y[i] + current_d[i])
            model.Add(x_end_j == x[j] + current_w[j])
            model.Add(y_end_j == y[j] + current_d[j])

            # Geometry Logic
            model.Add(x_end_i <= x[j]).OnlyEnforceIf(left)
            model.Add(x_end_j <= x[i]).OnlyEnforceIf(right)
            model.Add(y_end_i <= y[j]).OnlyEnforceIf(behind)
            model.Add(y_end_j <= y[i]).OnlyEnforceIf(front)
            model.Add(z[i] + items[i].h <= z[j]).OnlyEnforceIf(below)
            model.Add(z[j] + items[j].h <= z[i]).OnlyEnforceIf(above)

            # Ensure they don't overlap
            model.AddBoolOr([left, right, behind, front, below, above]).OnlyEnforceIf([is_packed[i], is_packed[j]])

            # --- SMART PHYSICS CONSTRAINTS ---

            # Rule 1: HEAVIEST ON BOTTOM (Strict)
            # If Item I is heavier, it CANNOT be on top of J
            if items[i].weight > items[j].weight:
                model.Add(above == False)
            elif items[j].weight > items[i].weight:
                model.Add(below == False)

            # Rule 2: BIGGEST AREA ON BOTTOM (Relaxed)
            # Prevent large items on top... UNLESS they are very light.
            
            # If I is Bigger Area than J
            if items[i].area > items[j].area * 1.2:
                # Only forbid if I is heavy (> 60% of J's weight)
                if items[i].weight > items[j].weight * 0.6: 
                     model.Add(above == False)
            
            # If J is Bigger Area than I
            elif items[j].area > items[i].area * 1.2:
                if items[j].weight > items[i].weight * 0.6:
                    model.Add(below == False)

    # --- 3. OBJECTIVE (Density) ---
    volume_score = 0
    gravity_score = 0
    
    for i, item in enumerate(items):
        # Reward packing items
        volume_score += (is_packed[i] * item.volume)
        # Penalize height (Gravity)
        gravity_score += z[i]
    
    # Formula: Maximize Volume - Minimize Peak Height - Minimize Total Height
    model.Maximize(
        (volume_score * 100000) - (max_z * 1000) - gravity_score
    )

    # --- 4. SOLVE ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0 
    solver.parameters.num_search_workers = 8 
    
    status = solver.Solve(model)

    packed_items_data = []
    unpacked_indices = []
    
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for i, item in enumerate(items):
            if solver.BooleanValue(is_packed[i]):
                # Resolve final dimensions
                final_w = item.w if solver.Value(rotation[i]) == 0 else item.d
                final_d = item.d if solver.Value(rotation[i]) == 0 else item.w
                
                packed_items_data.append({
                    "id": item.id,
                    "name": item.name,
                    "x": solver.Value(x[i]),
                    "y": solver.Value(y[i]),
                    "z": solver.Value(z[i]),
                    "w": final_w, 
                    "h": item.h, 
                    "d": final_d, 
                    "weight": item.weight,
                    "rotated": bool(solver.Value(rotation[i]))
                })
            else:
                unpacked_indices.append(i)
    else:
        unpacked_indices = list(range(len(items)))
    
    return packed_items_data, unpacked_indices


# --- 3. MULTI-PALLET LOOP ---
def solve_multiple_pallets(items, pallet_w, pallet_d, pallet_h):
    all_pallets = []
    
    # Sort items: Heaviest + Largest Volume first
    # This helps the solver find the "base" layer easier
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

# --- 4. TEST EXECUTION ---
if __name__ == "__main__":
    # Test Data: A mix of Heavy bases, Light/Large tops, and fillers
    all_items = [
        # Heavy Bases (Should be on bottom)
        Item("Heavy1", "Heavy Base 1", 45, 45, 20, weight=98),
        Item("Heavy2", "Heavy Base 2", 45, 45, 20, weight=99),
        Item("Heavy3", "Heavy Base 3", 45, 45, 20, weight=101),
        Item("Heavy4", "Heavy Base 4", 45, 45, 20, weight=97),

        # The Problem Item: Light but Huge (Should stack on top now)
        Item("Flat", "Flat Item", 60, 60, 5, weight=20),
        
        # Fillers
        Item("Anvil", "Heavy Anvil", 10, 10, 10, weight=50), 
        Item("Med1", "Normal Box", 20, 20, 20, weight=10),
        Item("Med2", "Normal Box", 20, 20, 20, weight=10),
        Item("Tall", "Tall Item", 10, 10, 60, weight=15),
    ]

    print("=" * 60)
    print("SMART DENSITY BIN PACKING SOLVER")
    print("=" * 60)

    final_manifest = solve_multiple_pallets(all_items, 100, 100, 100)

    print("\n" + "=" * 60)
    print("FINAL RESULT (JSON):")
    print("=" * 60)
    print(json.dumps(final_manifest, indent=2))