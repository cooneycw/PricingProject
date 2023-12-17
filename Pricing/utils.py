def reverse_pv_index(group):
    group['new_pv_index'] = group['pv_index'].values[::-1]
    return group
