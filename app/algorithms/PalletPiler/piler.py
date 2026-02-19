from ortools.sat.python import cp_model
import json
import os

# --- 1. DATA STRUCTURE ---
class Item:
    # UPDATED: Added type_id and location as optional arguments
    def __init__(self, id, name, w, d, h, weight, picking_order=1, allow_tipping=True, is_fragile=False, type_id=None, location=""):
        self.id = str(id)
        self.name = name
        self.w = w
        self.d = d
        self.h = h
        self.dims = [w, d, h]
        
        self.weight = weight 
        self.volume = w * d * h
        
        self.picking_order = picking_order
        self.allow_tipping = allow_tipping
        self.is_fragile = is_fragile
        self.location = location
        
        # FIX: Prefer explicit type_id, otherwise handle dashes correctly
        if type_id:
            self.type_id = type_id
        else:
            # Fallback: Split by the LAST dash to remove the index (e.g. "SKU-1" -> "SKU")
            self.type_id = self.id.rsplit('-', 1)[0] if '-' in self.id else self.id

# --- 2. CORE SOLVER LOGIC ---
def solve_single_pallet(items, pallet_w, pallet_d, pallet_h, 
                        gravity_weight=150, 
                        corner_weight=2, 
                        clustering_weight=1, 
                        max_z_penalty=4580,
                        location_weight=200):
    
    model = cp_model.CpModel()

    # --- CONSTANTS ---
    MAX_H_TO_BASE_RATIO = 3.0 
    OVERHANG_RATIO = 5 
    GAP_FILL_PENALTY = 10000   # Heavy cost to tip a box; solver only tips to fill gaps
    SAME_TYPE_STACKING_PENALTY = 1000 

    # --- Variables ---
    is_packed = {}
    x = {}
    y = {}
    z = {}
    orientation = {} 
    spin = {}
    
    current_w = {}
    current_d = {}
    current_h = {}
    current_area = {} 

    max_z = model.NewIntVar(0, pallet_h, 'max_z')

    # Clustering Helpers
    last_seen_index_by_name = {}
    total_clustering_dist = 0
    total_stacking_penalty = 0
    gap_fill = {}

    for i, item in enumerate(items):
        is_packed[i] = model.NewBoolVar(f'is_packed_{i}')
        x[i] = model.NewIntVar(0, pallet_w, f'x_{i}')
        y[i] = model.NewIntVar(0, pallet_d, f'y_{i}')
        z[i] = model.NewIntVar(0, pallet_h, f'z_{i}')
        spin[i] = model.NewBoolVar(f'spin_{i}')
        
        orientation[i] = [model.NewBoolVar(f'orient_{i}_{k}') for k in range(3)]
        model.Add(sum(orientation[i]) == 1).OnlyEnforceIf(is_packed[i])
        
        # --- UPRIGHT-FIRST CONSTRAINT ---
        # All boxes stay upright (orientation[0]) by default.
        # Tipping (orientation[1] or [2]) is only unlocked via gap_fill,
        # which carries a heavy penalty so the solver only tips to fill gaps.
        if item.allow_tipping:
            gap_fill[i] = model.NewBoolVar(f'gap_fill_{i}')
            model.Add(orientation[i][0] == 1).OnlyEnforceIf(gap_fill[i].Not())
            model.AddImplication(gap_fill[i], is_packed[i])
        else:
            # Items that must never tip — always upright, gap_fill disabled
            model.Add(orientation[i][0] == 1)
            gap_fill[i] = None

        # --- PHYSICS CHECKS ---
        w, d, h = item.dims
        if h > min(w, d) * MAX_H_TO_BASE_RATIO:
            model.Add(orientation[i][0] == 0)
        if item.allow_tipping:
            if w > min(h, d) * MAX_H_TO_BASE_RATIO:
                model.Add(orientation[i][1] == 0)
            if d > min(w, h) * MAX_H_TO_BASE_RATIO:
                model.Add(orientation[i][2] == 0)

        # --- CLUSTERING LOGIC ---
        if item.name in last_seen_index_by_name:
            prev_i = last_seen_index_by_name[item.name]
            
            c_dx = model.NewIntVar(0, pallet_w, f'cdx_{i}')
            c_dy = model.NewIntVar(0, pallet_d, f'cdy_{i}')
            c_dz = model.NewIntVar(0, pallet_h, f'cdz_{i}')
            
            model.Add(c_dx >= x[i] - x[prev_i]).OnlyEnforceIf([is_packed[i], is_packed[prev_i]])
            model.Add(c_dx >= x[prev_i] - x[i]).OnlyEnforceIf([is_packed[i], is_packed[prev_i]])
            model.Add(c_dy >= y[i] - y[prev_i]).OnlyEnforceIf([is_packed[i], is_packed[prev_i]])
            model.Add(c_dy >= y[prev_i] - y[i]).OnlyEnforceIf([is_packed[i], is_packed[prev_i]])
            model.Add(c_dz >= z[i] - z[prev_i]).OnlyEnforceIf([is_packed[i], is_packed[prev_i]])
            model.Add(c_dz >= z[prev_i] - z[i]).OnlyEnforceIf([is_packed[i], is_packed[prev_i]])
            
            total_clustering_dist += (c_dx + c_dy + (c_dz * 4))
            
        last_seen_index_by_name[item.name] = i

    # --- DIMENSION MAPPING ---
    for i, item in enumerate(items):
        w, d, h = item.dims
        max_dim = max(w, d, h)
        current_w[i] = model.NewIntVar(0, max_dim, f'cw_{i}')
        current_d[i] = model.NewIntVar(0, max_dim, f'cd_{i}')
        current_h[i] = model.NewIntVar(0, max_dim, f'ch_{i}')
        areas = [w*d, h*d, w*h]
        current_area[i] = model.NewIntVar(min(areas), max(areas), f'area_{i}')

        # Orientations
        model.Add(current_w[i] == w).OnlyEnforceIf([orientation[i][0], spin[i].Not()])
        model.Add(current_d[i] == d).OnlyEnforceIf([orientation[i][0], spin[i].Not()])
        model.Add(current_w[i] == d).OnlyEnforceIf([orientation[i][0], spin[i]])
        model.Add(current_d[i] == w).OnlyEnforceIf([orientation[i][0], spin[i]])
        model.Add(current_h[i] == h).OnlyEnforceIf(orientation[i][0])
        model.Add(current_area[i] == w*d).OnlyEnforceIf(orientation[i][0])

        model.Add(current_w[i] == h).OnlyEnforceIf([orientation[i][1], spin[i].Not()])
        model.Add(current_d[i] == d).OnlyEnforceIf([orientation[i][1], spin[i].Not()])
        model.Add(current_w[i] == d).OnlyEnforceIf([orientation[i][1], spin[i]])
        model.Add(current_d[i] == h).OnlyEnforceIf([orientation[i][1], spin[i]])
        model.Add(current_h[i] == w).OnlyEnforceIf(orientation[i][1])
        model.Add(current_area[i] == h*d).OnlyEnforceIf(orientation[i][1])

        model.Add(current_w[i] == w).OnlyEnforceIf([orientation[i][2], spin[i].Not()])
        model.Add(current_d[i] == h).OnlyEnforceIf([orientation[i][2], spin[i].Not()])
        model.Add(current_w[i] == h).OnlyEnforceIf([orientation[i][2], spin[i]])
        model.Add(current_d[i] == w).OnlyEnforceIf([orientation[i][2], spin[i]])
        model.Add(current_h[i] == d).OnlyEnforceIf(orientation[i][2])
        model.Add(current_area[i] == w*h).OnlyEnforceIf(orientation[i][2])

        # Boundaries
        model.Add(x[i] + current_w[i] <= pallet_w).OnlyEnforceIf(is_packed[i])
        model.Add(y[i] + current_d[i] <= pallet_d).OnlyEnforceIf(is_packed[i])
        model.Add(z[i] + current_h[i] <= pallet_h).OnlyEnforceIf(is_packed[i])
        model.Add(max_z >= z[i] + current_h[i]).OnlyEnforceIf(is_packed[i])

    # --- COLLISION & SUPPORT ---
    for i in range(len(items)):
        supported_by = []  # Initialize support list for each item
        
        for j in range(len(items)):
            if i == j: continue

            left = model.NewBoolVar(f'{i}_left_{j}')
            right = model.NewBoolVar(f'{i}_right_{j}')
            behind = model.NewBoolVar(f'{i}_behind_{j}')
            front = model.NewBoolVar(f'{i}_front_{j}')
            below = model.NewBoolVar(f'{i}_below_{j}')
            above = model.NewBoolVar(f'{i}_above_{j}')

            model.Add(x[i] + current_w[i] <= x[j]).OnlyEnforceIf(left)
            model.Add(x[j] + current_w[j] <= x[i]).OnlyEnforceIf(right)
            model.Add(y[i] + current_d[i] <= y[j]).OnlyEnforceIf(behind)
            model.Add(y[j] + current_d[j] <= y[i]).OnlyEnforceIf(front)
            model.Add(z[i] + current_h[i] <= z[j]).OnlyEnforceIf(below)
            model.Add(z[j] + current_h[j] <= z[i]).OnlyEnforceIf(above)

            model.AddBoolOr([left, right, behind, front, below, above]).OnlyEnforceIf([is_packed[i], is_packed[j]])

            # Location ordering: items picked first (lower picking_order) must stay below
            if items[i].picking_order < items[j].picking_order:
                model.Add(above == False)
            elif items[i].picking_order > items[j].picking_order:
                model.Add(below == False)
            
            # Fragile Rule
            if items[j].is_fragile:
                model.Add(above == False)
            if items[i].is_fragile:
                model.Add(below == False)

            # --- TOWER PREVENTION (FIXED) ---
            # Now that type_id is correct, this will correctly penalize stacking "Winter Jacket" on "Winter Jacket"
            if items[i].type_id == items[j].type_id:
                 i_stacked_on_j = model.NewBoolVar(f'{i}_stack_{j}')
                 model.Add(above == True).OnlyEnforceIf(i_stacked_on_j)
                 model.Add(above == False).OnlyEnforceIf(i_stacked_on_j.Not())
                 total_stacking_penalty += i_stacked_on_j

            # Support Logic
            x_supported = model.NewBoolVar(f'{i}_x_sup_{j}')
            y_supported = model.NewBoolVar(f'{i}_y_sup_{j}')
            
            tol_w = model.NewIntVar(0, pallet_w, f'tol_w_{i}')
            tol_d = model.NewIntVar(0, pallet_d, f'tol_d_{i}')
            model.AddDivisionEquality(tol_w, current_w[i] * OVERHANG_RATIO, 100)
            model.AddDivisionEquality(tol_d, current_d[i] * OVERHANG_RATIO, 100)

            model.Add(x[i] >= x[j] - tol_w).OnlyEnforceIf(x_supported)
            model.Add(x[i] + current_w[i] <= x[j] + current_w[j] + tol_w).OnlyEnforceIf(x_supported)
            model.Add(y[i] >= y[j] - tol_d).OnlyEnforceIf(y_supported)
            model.Add(y[i] + current_d[i] <= y[j] + current_d[j] + tol_d).OnlyEnforceIf(y_supported)
            
            is_valid_base = model.NewBoolVar(f'{i}_on_{j}')
            model.AddBoolAnd([above, x_supported, y_supported]).OnlyEnforceIf(is_valid_base)
            model.Add(z[i] == z[j] + current_h[j]).OnlyEnforceIf(is_valid_base)
            # Prevent Ghost Supports: if is_valid_base is true, then is_packed[j] must be true
            model.AddImplication(is_valid_base, is_packed[j])
            
            supported_by.append(is_valid_base)

        on_ground = model.NewBoolVar(f'{i}_on_ground')
        model.Add(z[i] == 0).OnlyEnforceIf(on_ground)
        model.AddBoolOr([on_ground] + supported_by).OnlyEnforceIf(is_packed[i])

    # --- OBJECTIVE FUNCTION ---
    volume_score = 0
    gravity_score = 0
    corner_score = 0
    gap_fill_total = 0
    location_order_score = 0
    
    max_picking_order = max((item.picking_order for item in items), default=1)
    
    for i, item in enumerate(items):
        volume_score += (is_packed[i] * item.volume)
        gravity_score += (z[i] * gravity_weight) 
        corner_score += (x[i] + y[i]) 

        # Count gap-fill tipping (only for items that allow tipping)
        if gap_fill[i] is not None:
            gap_fill_total += gap_fill[i]
        
        # Items picked first (lower picking_order) get a stronger penalty for being high up.
        # This encourages them to spread out horizontally and form a stable base.
        order_factor = max_picking_order - item.picking_order + 1
        location_order_score += z[i] * order_factor

    model.Maximize(
        (volume_score * 1000) 
        - (max_z * max_z_penalty) 
        - gravity_score 
        - (corner_score * corner_weight) 
        - (gap_fill_total * GAP_FILL_PENALTY)
        - (total_clustering_dist * clustering_weight)
        - (total_stacking_penalty * SAME_TYPE_STACKING_PENALTY) 
        - (location_order_score * location_weight)
    )

    # --- SOLVE ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 20.0 
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
                    "type_id": item.type_id,
                    "location": item.location,
                    "picking_order": item.picking_order,
                    "x": solver.Value(x[i]),
                    "y": solver.Value(y[i]),
                    "z": solver.Value(z[i]),
                    "w": solver.Value(current_w[i]), 
                    "h": solver.Value(current_h[i]), 
                    "d": solver.Value(current_d[i]), 
                    "weight": item.weight,
                    "tipped": not (solver.BooleanValue(orientation[i][0])) 
                })
            else:
                unpacked_indices.append(i)
                
        packed_items_data.sort(key=lambda item: (item['z'], item['y'], item['x']))
        
    else:
        unpacked_indices = list(range(len(items)))
    
    return packed_items_data, unpacked_indices

def solve_multiple_pallets(items, pallet_w, pallet_d, pallet_h, **kwargs):
    all_pallets = []
    items.sort(key=lambda x: (x.picking_order, -(x.w * x.d), x.name))
    remaining_items = items.copy()
    pallet_number = 1
    
    while len(remaining_items) > 0:
        packed, unpacked_indices = solve_single_pallet(remaining_items, pallet_w, pallet_d, pallet_h, **kwargs)
        if len(packed) == 0: break
        all_pallets.append({"pallet_id": pallet_number, "items": packed})
        remaining_items = [remaining_items[i] for i in unpacked_indices]
        pallet_number += 1
    return all_pallets