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


def perform_logistic_regression(data, reform_fact):
    df = pd.DataFrame(data, columns=['Year', 'Value'])
    df['Ln_Value'] = np.log(df['Value'])
    proj_year = max(df['Year'].values) + 1

    reform = False
    if sum(reform_fact) != len(reform_fact) and sum(reform_fact) > 0:
        new_reform_fact = [0] * len(reform_fact)
        for i in range(len(reform_fact)):
            if reform_fact[i] == 1:
                reform = True
            if reform:
                new_reform_fact[0:i + 1] = [1] * (i + 1)
                break
        df['Reform'] = new_reform_fact

    if reform:
        feature_names = ['Year', 'Reform']
    else:
        feature_names = ['Year']

    X = df[feature_names]
    y = df['Ln_Value']

    model = LinearRegression(fit_intercept=True)
    model.fit(X, y)

    if reform:
        pred_df = df.drop(columns=['Ln_Value', 'Value'])
        new_row_a = {'Year': proj_year, 'Reform': 1}
        new_row_b = {'Year': proj_year, 'Reform': 0}
        pred_df = pd.concat([pred_df, pd.DataFrame([new_row_a]), pd.DataFrame([new_row_b])], ignore_index=True)
        pred_df = pred_df.sort_values(by=['Year', 'Reform'], ascending=[True, True])
        predicted_ln_value = model.predict(pred_df)
        predicted_value = np.exp(predicted_ln_value)
        last_yr_reform = predicted_value[len(predicted_value) - 1]
        last_yr_no_reform = predicted_value[len(predicted_value) - 2]
        prior_yr_reform = predicted_value[len(predicted_value) - 3]
        if prior_yr_reform != 0:
            est = [last_yr_reform / prior_yr_reform - 1]
        else:
            est = [0]
        if last_yr_no_reform != 0:
            est.append(last_yr_reform / last_yr_no_reform - 1)
        else:
            est.append(0)

        ret_preds = list(predicted_value[0:len(reform_fact)])
        ret_preds.append(predicted_value[-1])
        return reform, est, ret_preds
    else:
        df = df.drop(columns=['Ln_Value', 'Value'])
        new_row_a = {'Year': 2023}
        df = pd.concat([df, pd.DataFrame([new_row_a])], ignore_index=True)
        df = df.sort_values(by=['Year'], ascending=[True])
        predicted_ln_value = model.predict(df)
        predicted_value = np.exp(predicted_ln_value)
        last_yr_no_reform = predicted_value[len(predicted_value) - 1]
        prior_yr_no_reform = predicted_value[len(predicted_value) - 2]
        if last_yr_no_reform != 0:
            est = [last_yr_no_reform / prior_yr_no_reform - 1]
        else:
            est = [0]

        ret_preds = list(predicted_value[0:len(reform_fact)])
        ret_preds.append(predicted_value[-1])
        return reform, est, ret_preds
