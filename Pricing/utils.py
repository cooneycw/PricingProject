import math


def reverse_pv_index(group):
    group['new_pv_index'] = group['pv_index'].values[::-1]
    return group


def calculate_growth_rate(row, latest_year, earliest_year):
    g = min(0.07, max(-0.07, (row['in_force'] / row['beg_in_force']) ** (latest_year - earliest_year) - 1))
    return g


def calculate_avg_profit(row, latest_year, earliest_year):
    if row['tot_in_force'] == 0:
        row['tot_in_force'] = 0
    avg_profit = row['profit'] / row['tot_in_force']
    return avg_profit


def calculate_future_value(row, latest_year, earliest_year, irr):
    result = row['in_force'] * row['avg_profit'] / (irr - row['capped_growth_rate'])
    return result
