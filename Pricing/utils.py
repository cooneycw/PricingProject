import math
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from decimal import Decimal


def reverse_pv_index(group):
    group['new_pv_index'] = group['pv_index'].values[::-1]
    return group


def calculate_growth_rate(row, latest_year, earliest_year):
    g = min(0.07, max(-0.07, (row['in_force'] / row['beg_in_force']) ** (latest_year - earliest_year) - 1))
    return Decimal(g)


def calculate_avg_profit(row, latest_year, earliest_year):
    if row['tot_in_force'] == 0:
        row['tot_in_force'] = 0
    avg_profit = row['profit'] / row['tot_in_force']
    return avg_profit


def calculate_future_value(row, latest_year, earliest_year, irr):
    result = row['in_force'] * row['avg_profit'] / (irr - row['capped_growth_rate'])
    return result


def perform_logistic_regression(proj_year, data):
    df = pd.DataFrame(data, columns=['Year', 'Value'])
    df['Ln_Value'] = np.log(df['Value'])
    feature_names = ['Year']
    X = df[feature_names]
    y = df['Ln_Value']

    model = LinearRegression()
    model.fit(X, y)

    proj_data = pd.DataFrame([[proj_year]], columns=feature_names)
    predicted_ln_value = model.predict(proj_data)

    predicted_value = np.exp(predicted_ln_value)
    return predicted_value
