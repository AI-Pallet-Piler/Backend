from ortools.sat.python import cp_model
import json
import os
from datetime import datetime

# This file will output a json when run

# --- 1. DATA STRUCTURE ---
class Item:
    def __init__(self, id, name, w, d, h, weight, allow_tipping=True):
        self.id = id
        self.name = name
        # We store original dimensions
        self.dims = [w, d, h]
        self.weight = weight 
        self.volume = w * d * h
        # Can this item be tipped over? (e.g. Fridge = False, Box = True)
        self.allow_tipping = allow_tipping

# --- 2. CORE SOLVER LOGIC ---
def solve_single_pallet(items, pallet_w, pallet_d, pallet_h):
    """
    Attempts to pack items with FULL 3D ROTATION (Spin + Tip).
    """
    model = cp_model.CpModel()

    # --- Variables ---
    is_packed = {}
    x = {}
    y = {}
    z = {}
    
    # Orientation Variables:
    # We need to decide which dimension is Vertical (H), and which are Horizontal (W, D)
    # 0: Upright (H is H)
    # 1: Tipped on Side (W is H)
    # 2: Tipped on Front (D is H)
    orientation = {} 
    
    # Spin Variable (Rotation on floor):
    # False: Keep standard W/D
    # True: Swap W/D
    spin = {}

    max_z = model.NewIntVar(0, pallet_h, 'max_z')

    for i, item in enumerate(items):
        is_packed[i] = model.NewBoolVar(f'is_packed_{i}')
        x[i] = model.NewIntVar(0, pallet_w, f'x_{i}')
        y[i] = model.NewIntVar(0, pallet_d, f'y_{i}')
        z[i] = model.NewIntVar(0, pallet_h, f'z_{i}')
        
        spin[i] = model.NewBoolVar(f'spin_{i}')
        
        # Define 3 booleans for the 3 tipping states
        # We use a list [b0, b1, b2] where exactly one must be true
        orientation[i] = [model.NewBoolVar(f'orient_{i}_{k}') for k in range(3)]
        
        # Constraint: Exactly one orientation must be selected
        model.Add(sum(orientation[i]) == 1).OnlyEnforceIf(is_packed[i])
        
        # If tipping is disabled, force orientation[0] (Upright) to be true
        if not item.allow_tipping:
            model.Add(orientation[i][0] == 1)

    # --- Constraints ---

    # A. Effective Dimensions (The Magic Part)
    # We create variables for the ACTUAL shape of the box as it sits on the pallet
    current_w = {}
    current_d = {}
    current_h = {}
    current_area = {}

    for i, item in enumerate(items):
        w, d, h = item.dims
        
        # Create integer variables for the final dimensions
        # The max dimension could be any of w, d, h
        max_dim = max(w, d, h)
        current_w[i] = model.NewIntVar(0, max_dim, f'cw_{i}')
        current_d[i] = model.NewIntVar(0, max_dim, f'cd_{i}')
        current_h[i] = model.NewIntVar(0, max_dim, f'ch_{i}')
        
        # Area is needed for stability logic. 
        # Since W*D is quadratic, we pre-calculate the 3 possible base areas.
        # Area 0 (Upright): w*d
        # Area 1 (Side):    h*d
        # Area 2 (Front):   w*h
        areas = [w*d, h*d, w*h]
        current_area[i] = model.NewIntVar(min(areas), max(areas), f'area_{i}')

        # --- LOGIC MAPPING ---
        # 1. HEIGHT MAPPING
        # If Orient 0: H = h
        model.Add(current_h[i] == h).OnlyEnforceIf(orientation[i][0])
        # If Orient 1: H = w
        model.Add(current_h[i] == w).OnlyEnforceIf(orientation[i][1])
        # If Orient 2: H = d
        model.Add(current_h[i] == d).OnlyEnforceIf(orientation[i][2])

        # 2. WIDTH / DEPTH MAPPING (With Spin)
        # This is complex because we have 6 combinations.
        # We simplify by defining "Base Dimensions" first, then swapping them if spin=True.
        
        # If Orient 0 (Upright): Base is w, d
        model.Add(current_w[i] == w).OnlyEnforceIf([orientation[i][0], spin[i].Not()])
        model.Add(current_d[i] == d).OnlyEnforceIf([orientation[i][0], spin[i].Not()])
        model.Add(current_w[i] == d).OnlyEnforceIf([orientation[i][0], spin[i]]) # Spun
        model.Add(current_d[i] == w).OnlyEnforceIf([orientation[i][0], spin[i]]) # Spun
        model.Add(current_area[i] == w*d).OnlyEnforceIf(orientation[i][0])

        # If Orient 1 (Side - W is vertical): Base is h, d
        model.Add(current_w[i] == h).OnlyEnforceIf([orientation[i][1], spin[i].Not()])
        model.Add(current_d[i] == d).OnlyEnforceIf([orientation[i][1], spin[i].Not()])
        model.Add(current_w[i] == d).OnlyEnforceIf([orientation[i][1], spin[i]]) # Spun
        model.Add(current_d[i] == h).OnlyEnforceIf([orientation[i][1], spin[i]]) # Spun
        model.Add(current_area[i] == h*d).OnlyEnforceIf(orientation[i][1])

        # If Orient 2 (Front - D is vertical): Base is w, h
        model.Add(current_w[i] == w).OnlyEnforceIf([orientation[i][2], spin[i].Not()])
        model.Add(current_d[i] == h).OnlyEnforceIf([orientation[i][2], spin[i].Not()])
        model.Add(current_w[i] == h).OnlyEnforceIf([orientation[i][2], spin[i]]) # Spun
        model.Add(current_d[i] == w).OnlyEnforceIf([orientation[i][2], spin[i]]) # Spun
        model.Add(current_area[i] == w*h).OnlyEnforceIf(orientation[i][2])

        # --- BOUNDARIES ---
        model.Add(x[i] + current_w[i] <= pallet_w).OnlyEnforceIf(is_packed[i])
        model.Add(y[i] + current_d[i] <= pallet_d).OnlyEnforceIf(is_packed[i])
        model.Add(z[i] + current_h[i] <= pallet_h).OnlyEnforceIf(is_packed[i])
        
        model.Add(max_z >= z[i] + current_h[i]).OnlyEnforceIf(is_packed[i])

    # B. Pairwise Non-Overlap & Physics
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            
            left = model.NewBoolVar(f'{i}_left_{j}')
            right = model.NewBoolVar(f'{i}_right_{j}')
            behind = model.NewBoolVar(f'{i}_behind_{j}')
            front = model.NewBoolVar(f'{i}_front_{j}')
            below = model.NewBoolVar(f'{i}_below_{j}')
            above = model.NewBoolVar(f'{i}_above_{j}')

            # Map coordinates to End variables for collision checking
            x_end_i = model.NewIntVar(0, pallet_w, f'xe_{i}')
            y_end_i = model.NewIntVar(0, pallet_d, f'ye_{i}')
            x_end_j = model.NewIntVar(0, pallet_w, f'xe_{j}')
            y_end_j = model.NewIntVar(0, pallet_d, f'ye_{j}')

            model.Add(x_end_i == x[i] + current_w[i])
            model.Add(y_end_i == y[i] + current_d[i])
            model.Add(x_end_j == x[j] + current_w[j])
            model.Add(y_end_j == y[j] + current_d[j])

            # Geometry
            model.Add(x_end_i <= x[j]).OnlyEnforceIf(left)
            model.Add(x_end_j <= x[i]).OnlyEnforceIf(right)
            model.Add(y_end_i <= y[j]).OnlyEnforceIf(behind)
            model.Add(y_end_j <= y[i]).OnlyEnforceIf(front)
            # Note: For Z, we use current_h, not item.h!
            model.Add(z[i] + current_h[i] <= z[j]).OnlyEnforceIf(below)
            model.Add(z[j] + current_h[j] <= z[i]).OnlyEnforceIf(above)

            model.AddBoolOr([left, right, behind, front, below, above]).OnlyEnforceIf([is_packed[i], is_packed[j]])

            # --- SMART PHYSICS ---

            # Rule 1: HEAVIEST ON BOTTOM
            if items[i].weight > items[j].weight:
                model.Add(above == False)
            elif items[j].weight > items[i].weight:
                model.Add(below == False)

            # Rule 2: BIGGEST AREA ON BOTTOM (Dynamic!)
            # We now use 'current_area' because if we tip a box, its area changes!
            # Since current_area is a variable, we can't use Python 'if'. 
            # We must use Solver Constraints.
            
            # This is complex in CP-SAT (Variable > Variable condition).
            # To keep performance high, we simplify: 
            # We assume the "Smart Stability" rule only cares about significant size diffs.
            # We skip adding constraints for similar-sized items to save computation.
            # But for obvious ones (Plate vs Cube), we enforce it.
            
            # Since we can't iterate variables, we add a conditional enforcement:
            # "If Area(I) > Area(J) * 1.2 AND Weight(I) is Heavy -> Forbidden Above"
            
            # IMPLEMENTATION:
            # We define boolean: i_is_bigger
            i_is_bigger = model.NewBoolVar(f'{i}_bigger_{j}')
            model.Add(current_area[i] >= current_area[j] + 100).OnlyEnforceIf(i_is_bigger) # +100 as a buffer
            model.Add(current_area[i] < current_area[j] + 100).OnlyEnforceIf(i_is_bigger.Not())
            
            # If I is Bigger, forbid it from being above (unless it's light)
            if items[i].weight > items[j].weight * 0.6:
                model.Add(above == False).OnlyEnforceIf(i_is_bigger)
                
            # Inverse for J
            j_is_bigger = model.NewBoolVar(f'{j}_bigger_{i}')
            model.Add(current_area[j] >= current_area[i] + 100).OnlyEnforceIf(j_is_bigger)
            model.Add(current_area[j] < current_area[i] + 100).OnlyEnforceIf(j_is_bigger.Not())
            
            if items[j].weight > items[i].weight * 0.6:
                model.Add(below == False).OnlyEnforceIf(j_is_bigger)


    # --- 3. OBJECTIVE ---
    volume_score = 0
    gravity_score = 0
    
    for i, item in enumerate(items):
        volume_score += (is_packed[i] * item.volume)
        gravity_score += z[i]
    
    # Maximize Volume, Minimize Max Z, Minimize Gravity
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
                packed_items_data.append({
                    "id": item.id,
                    "name": item.name,
                    "x": solver.Value(x[i]),
                    "y": solver.Value(y[i]),
                    "z": solver.Value(z[i]),
                    "w": solver.Value(current_w[i]), 
                    "h": solver.Value(current_h[i]), 
                    "d": solver.Value(current_d[i]), 
                    "weight": item.weight,
                    # Helper for debugging visualization
                    "tipped": not (solver.BooleanValue(orientation[i][0])) 
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
        
        next_batch = [remaining_items[i] for i in unpacked_indices]
        remaining_items = next_batch
        
        pallet_number += 1
    
    return all_pallets