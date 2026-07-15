#import os
#import re
#import sys
#import json
#import requests
#from io import StringIO
from datetime import datetime,date, timedelta
import calendar
import pandas_market_calendars as mcal
from IPython.display import Markdown as md, display
from dateutil.relativedelta import relativedelta
import pandas as pd
from pandas.tseries.holiday import GoodFriday
import numpy as np
from scipy.optimize import minimize
from scipy import optimize
#import openpyxl
#from openpyxl.utils import get_column_letter
from IPython.display import display, Markdown as md, HTML
import unicodedata

def scheduled_pay_dates(last_date,settlement=None,freq=2):
  '''
    Generates a chronological list of coupon payment dates from settlement to last_date.
    The function calculates dates backward from the last_date date based on the
    specified frequency. It handles standard bond market "end-of-month" logic:
    if the last_date date is the last day of a month, all preceding coupon payments
    are snapped to the last day of their respective months.
    Args:
        last_date (datetime.date,timestamp, or datetime64): The last date checked.
            Accepts a date object.
        settlement (datetime.date,timestamp, or datetime64): The settlement date (start of analysis).
            Coupons falling before this date are excluded. Defaults to date.today().
        freq (int, optional): The number of coupon payments per year.
            Accepted values:
            * 1: Annual, 2: Semi-Annual (Default), 4: Quarterly, 12: Monthly

    Returns:
        list[datetime.date]: A list of coupon dates sorted chronologically
        (earliest to latest), ending with the last_date date..
  '''



# convert settlement and last_date to datetime.date
  def make_date(date_value):
    if not isinstance(date_value,(datetime,date)):
      date_value=pd.Timestamp(date_value).date()
      return date_value
    # convert timestamps and datetimes to date
    else:
      try:
          return date_value.date()
      except:        
         return date_value


  #Validate the data- last_date, coupon, settlement, freq
  #last_date
  last_date=make_date(last_date)

  #settlement
  if settlement is None:
      settlement = date.today()
  else:
      settlement=make_date(settlement)
  #freq
  if int(freq) not in [1,2,4,12]:
      display(md(f"### ⚠️  your assigned freq {freq} it must be (1, 2, 4, or 12)\
     \n     semi-annual assumed (2)."))
      freq=int(2)

  # check last_date greater than settlement
  if last_date<=settlement:
    raise ValueError("last_date must be greater than the settlement date")

  # calculate the number of months between each coupon payment.
  num_months=int(12/freq)
 
  # timestamps so hat we can use pandas offset
  last_day=pd.Timestamp(last_date)
  settlement=pd.Timestamp(settlement)
  # raw_dates is a pandas datetime index that starts and goes 60 times
  # need to check for month_end and respect it (MonthsEnd)
  if last_day.is_month_end:
    raw_dates = pd.DatetimeIndex([last_day - pd.offsets.MonthEnd(num_months * i) for i in range(360)])
  else:
    raw_dates = pd.DatetimeIndex([last_day - pd.DateOffset(months=num_months * i) for i in range(360)])

  # only include dates greater than settlement date
  valid_dates=raw_dates[raw_dates>settlement]

  # convert timestamps back to date and make the order chronological with splice
  valid_dates=pd.to_datetime(valid_dates).date

  return valid_dates[::-1]

def adjust_bond_pay_dates(dates,calendar='SIFMAUS'):
  """
  Adjusts bond payment dates to account for holidays and weekends.
  dates can be a scalar, pandas series, or numpy array (datetime.date,timestamp, or datetime64)
  """



  # Ensure dates is a DatetimeIndex
  if not pd.api.types.is_scalar(dates):
      dates = pd.DatetimeIndex(pd.to_datetime(dates))
  else:
      dates = pd.DatetimeIndex(pd.to_datetime([dates]))
      
  sifma = mcal.get_calendar(calendar)
  sifma_holidays = sifma.holidays().holidays
  good_fridays = GoodFriday.dates('2000-01-01', '2060-12-31')

  # Convert to DatetimeIndex and use .union() (which automatically deduplicates and sorts)
  sifma_idx = pd.DatetimeIndex(sifma_holidays)
  gf_idx = pd.DatetimeIndex(good_fridays)
  master_bond_holidays = sifma_idx.union(gf_idx)

  # Create a CustomBusinessDay offset using the combined holidays
  numpy_holidays = master_bond_holidays.values.astype('datetime64[D]')

  # Use NumPy for lightning-fast, fully vectorized date math (No warnings!)
  actual_payment_dates = np.busday_offset(
      dates.values.astype('datetime64[D]'),
      offsets=0,
      roll='forward',
      holidays=numpy_holidays
  )
  
  final_dates = pd.to_datetime(actual_payment_dates).date

  return final_dates

def convert_isda(settlement, prev_coupon):


    # make sure settlement is date
    # if not pandas timestamp convert and make it a date
    def make_date(date_value):
      if not isinstance(date_value,(datetime,date)):
        date_value=pd.Timestamp(date_value).date()
        return date_value
      # convert timestamps and datetimes to date
      else:
        try:
            return date_value.date()
        except:        
           return date_value

    settlement=make_date(settlement)
    prev_coupon=make_date(prev_coupon)


    if prev_coupon.year == settlement.year:
        days_in_year = 366 if calendar.isleap(settlement.year) else 365
        actual_days = (settlement - prev_coupon).days
        return actual_days / days_in_year

    # ISDA Split: Pivot on Jan 1st of the second year
    pivot_date = date(settlement.year, 1, 1)

    # All days from the coupon up to midnight Jan 1st
    days_prev = (pivot_date - prev_coupon).days
    days_prev_year = 366 if calendar.isleap(prev_coupon.year) else 365
    prev_ratio = days_prev / days_prev_year

    # All days from Jan 1st to the accrual end
    days_settlement = (settlement- pivot_date).days
    days_in_settlement_year = 366 if calendar.isleap(settlement.year) else 365
    settlement_ratio = days_settlement / days_in_settlement_year

    return prev_ratio + settlement_ratio

def _30_360_(settlement,prev_coupon):


    # make sure settlement is date
    # if not pandas timestamp convert and make it a date
    def make_date(date_value):
      if not isinstance(date_value,(datetime,date)):
        date_value=pd.Timestamp(date_value).date()
        return date_value
      # convert timestamps and datetimes to date
      else:
        try:
            return date_value.date()
        except:        
           return date_value


    settlement=make_date(settlement)
    prev_coupon=make_date(prev_coupon)

    # initalize
    number_days=0

    # accounting for years
    number_days+=(settlement.year-prev_coupon.year)*360

    # accounting for months
    number_days+=(settlement.month-prev_coupon.month)*30

    # accounting for days
    # February is the exception
    # Function to check if a date is the last day of its month (Feb 28 or 29)
    def feb_end(date_value):
        # If month is 2, check if it's the last day using calendar.monthrange
        return date_value.month == 2 and date_value.day == calendar.monthrange(date_value.year,
                                                                               date_value.month)[1]
    # STEP 1: Normalize Previous Coupon Date
    # Rule: If it's the 31st OR the end of Feb, it's 30.
    if prev_coupon.day == 31 or feb_end(prev_coupon):
        prev_coupon_days = 30
    else:
        prev_coupon_days = prev_coupon.day

    # STEP 2: Conditional Settlement Date
    # Rule: If it's the 31st OR the end of Feb AND the start was 30, it's 30.
    if (settlement.day == 31 or feb_end(settlement)) and prev_coupon_days == 30:
        settlement_days = 30
    else:
        settlement_days = settlement.day

    number_days+=settlement_days-prev_coupon_days

    return number_days/360

def accrued_interest(maturity, coupon, day_type='Actual/Actual', settlement=None, freq=2):
    """
      Returns the accrued interest for a bond.  Returns the accrued interest for a bond.

       Returns the accrued interest for a bond.  Returns the accrued interest for a bond.

    Args:
        maturity (datetime.date,timestamp, or datetime64): The maturity date of the bond.
        coupon (float): The annual coupon rate (e.g., 0.05 for 5%).
        day_types:
            Actual/Actual, Actual/365, Actual/360. and 30/360.
        settlement ((datetime.date,timestamp, or datetime64), optional):
         The settlement date. Defaults to today.
        freq (int, optional):
        Coupon frequency per year: 1 (annual). 2 (semi-annual)
                                    4 (quarterly), 12 (monthly)
                                    Defaults to 2.
    """

    #Validate Data
    def validate_date(datetime_object):
      # check for datetime or date
      if not isinstance(datetime_object, (datetime, date)):
          raise TypeError("Input must be a datetime or date object.")
      # convert datetime to date
      if isinstance(datetime_object, datetime):
        datetime_object = datetime_object.date()
      return datetime_object
    maturity = validate_date(maturity)

    if settlement is None:
        settlement = date.today()
    else:
        settlement = validate_date(settlement)

    if freq not in [1, 2, 4, 12]:
        print(f"⚠️ Warning: Freq {freq} invalid. Assumed Semi-Annual (2).")
        freq = 2

    try:
        coupon = float(coupon)
        if coupon < 0: raise ValueError
    except:
        raise ValueError("Coupon must be a positive number.")

    # Define strategic_date
    # Get all the bond's potential payment dates in the next year
    mat_is_last=maturity.day==calendar.monthrange(maturity.year,maturity.month)[1]
    if mat_is_last:
      lastDay=calendar.monthrange(settlement.year+1,maturity.month)[1]
      strategic_date=date(settlement.year+1,maturity.month,lastDay)
    else:
     strategic_date=date(settlement.year+1,maturity.month,maturity.day)

    #The strategic date: minimum of actual and next year's maturity date
    strategic_date=min(maturity,strategic_date)
    pay_dates = scheduled_pay_dates(strategic_date, settlement=settlement, freq=freq)

    # Should sorted but check
    pay_dates.sort()

    # The first date after the settlement date is the next coupon date
    next_coupon = None
    for d in pay_dates:
        if d >= settlement:
            next_coupon = d
            break

    # Bond has matured or annual coupon is zero
    if next_coupon is None or coupon==0:
        return 0.0

    #Calculate Previous Coupon Date
    num_months = int(12 // freq)
    prev_coupon = next_coupon - relativedelta(months=num_months)

    # Check for Month End adjustment on the calculated previous date
    is_next_month_end = next_coupon.day == calendar.monthrange(maturity.year, maturity.month)[1]

    if is_next_month_end:
        last_day_of_prev_month = calendar.monthrange(prev_coupon.year, prev_coupon.month)[1]
        prev_coupon = date(prev_coupon.year, prev_coupon.month, last_day_of_prev_month)

    # The day a coupon is paid is also the first day of the new cycle.

    accrued_value = 0.0

    if day_type == 'Actual/Actual':
        days_since_last = (settlement - prev_coupon).days
        days_between = (next_coupon - prev_coupon).days
        #  (DaysHeld / DaysInPeriod)
        accural_ratio= days_since_last/days_between
        # Actual/Actual uses the coupon paid on the date
        accrued_value = (coupon / freq) * accural_ratio


    elif day_type == '30/360':
        accural_ratio =_30_360_(settlement,prev_coupon)
        # Formula: Coupon * accrural ratio
        accrued_value = coupon * accural_ratio

    elif day_type == 'Actual/360':
        days_since_last = (settlement - prev_coupon).days
        accural_ratio= days_since_last/360
      # Formula: Coupon * accrural ratio        
        accrued_value = coupon * accural_ratio

    elif day_type == 'Actual/365':
        accural_ratio = convert_isda(settlement,prev_coupon)
      # Formula: Coupon * accrural ratio        
        accrued_value = coupon * accural_ratio

    else:
        # Fallback
        print(f"⚠️ Warning: Unknown day_type {day_type}. Using Actual/Actual.")
        days_since_last = (settlement - prev_coupon).days
        days_between = (next_coupon - prev_coupon).days
        #  (DaysHeld / DaysInPeriod)
        accural_ratio= days_since_last/days_between
        # Actual/Actual uses the coupon paid on the date
        accrued_value = (coupon / freq) * (days_since_last / days_between)

    return accrued_value

def adjust_bond_pay_dates(dates,calendar='SIFMAUS'):
  """
  Adjusts bond payment dates to account for holidays and weekends.
  dates can be a scalar, pandas series, or numpy array (datetime.date,timestamp, or datetime64)
  """


  # Ensure dates is a DatetimeIndex
  if not pd.api.types.is_scalar(dates):
      dates = pd.DatetimeIndex(pd.to_datetime(dates))
  else:
      dates = pd.DatetimeIndex(pd.to_datetime([dates]))
      
  sifma = mcal.get_calendar(calendar)
  sifma_holidays = sifma.holidays().holidays
  good_fridays = GoodFriday.dates('2000-01-01', '2060-12-31')

  # Convert to DatetimeIndex and use .union() (which automatically deduplicates and sorts)
  sifma_idx = pd.DatetimeIndex(sifma_holidays)
  gf_idx = pd.DatetimeIndex(good_fridays)
  master_bond_holidays = sifma_idx.union(gf_idx)

  # Create a CustomBusinessDay offset using the combined holidays
  numpy_holidays = master_bond_holidays.values.astype('datetime64[D]')

  # Use NumPy for lightning-fast, fully vectorized date math (No warnings!)
  actual_payment_dates = np.busday_offset(
      dates.values.astype('datetime64[D]'),
      offsets=0,
      roll='forward',
      holidays=numpy_holidays
  )
  
  final_dates = pd.to_datetime(actual_payment_dates).date

  return final_dates
  
def bond_pay_data(maturity, coupon, settlement=None, freq=2):
    '''
    Function calculates payment Dates And Amounts.
    maturity is a datetime object and coupon is a real number.
    Required arguments are maturity and annual coupon.
    If provided, the value of settlement is a datetime object;
    otherwise defaults to date.today()
    freq defaults to semi-annual but accepts freq equal
    to 1 for annual, 2 for semi-annal, 4 for quarterly, and 12 for monthly.
    The function assumes a par value of 100.
    Returns Numpy arrays of dates and amounts.

    Raises:
        TypeError: If maturity or settlement are not datetime objects.
        ValueError: If inputs are not logically valid (e.g., negative coupon,
                    maturity before settlement).
    '''


    # Validate the data - maturity, coupon, settlement, freq
    def make_date(date_value):
      # datetime64 are conerted
      if not isinstance(date_value,(datetime,date)):
        try:
          date_value=pd.Timestamp(date_value).date()
        except Exception as e: # Catch anything else unexpected
          print(f"wrong type for settlement or maturity {e}")
  
        date_value=pd.Timestamp(settlement).date()
      # convert timestamps and datetimes to date
      else:
        try:
          date_value=date_value.date()
        except:
          pass
      return date_value

    # maturity
    maturity = make_date(maturity)

    # settlement
    if settlement is None:
        settlement = date.today()
    else:
        settlement = make_date(settlement)

    # coupon
    try:
        coupon = float(coupon)
        if coupon < 0:
            raise ValueError("coupon rate cannot be negative.")
    except (ValueError, TypeError):
        raise ValueError("coupon must be a valid number.")

    # freq
    if int(freq) not in [1, 2, 4, 12]:
        display(md(f"### ⚠️ your assigned freq {freq} it must be (1, 2, 4, or 12)\n ### semi-annual assumed (2)."))
        freq = int(2)

    # check maturity greater than settlement
    if maturity <= settlement:
        raise ValueError("maturity must be greater than the settlement date")

    if coupon == 0:
        # Adjust maturity for non-settlement day and return date and face value
        adjust_maturity = adjust_bond_pay_dates(maturity)
        return np.array(adjust_maturity), np.array([100.0])

    # get scheduled payment dates from helper function scheduled_pay_dates
    scheduled_dates = scheduled_pay_dates(maturity, settlement, freq)

    # Pandas DataFrame Settlement desired column
    pay_dates = adjust_bond_pay_dates(scheduled_dates)

    # calculate payments
    # coupon divided by freq at each date
    pay = np.full(len(pay_dates), coupon / freq)

    # Add principal payment as last cash payment
    pay[-1] += 100

    return pay_dates,pay

def create_payoff_df(df, settlement,OLS=False):
    adjusted_maturities = adjust_bond_pay_dates(list(df.index))
    all_maturities = set(adjusted_maturities)

    df_payoff_columns = sorted(all_maturities)
    df_payoff_index=[i for i in range(len(df.index))]

    df_payoff = pd.DataFrame(
        np.zeros((len(df), len(df_payoff_columns))),
        columns=df_payoff_columns,
        index=df_payoff_index
    )
    total_rows = len(df)
    # Define a clean, pleasing HTML template for our status box
    def status_box(current, total):
        return f"""
        <div style="font-family: Arial, sans-serif; padding: 10px 15px; background-color: #f8f9fa; 
                    border-left: 4px solid #007bff; border-radius: 4px; width: fit-content; color: #333;">
            <b style="color: #007bff;">⚙️ Processing Bonds:</b> {current} of {total} added to DataFrame
        </div>
        """
    
    # initial display showing 0 bonds added
    progress_ui = display(HTML(status_box(0, total_rows)), display_id=True)

    for index,(maturity, coupon) in enumerate(zip(df.index, df['Coupon'])):

        # bond_pay_data returns payment dates and amounts
        row_pay_data = bond_pay_data(maturity, coupon, settlement=settlement)

        # Find any dates that aren't already columns
        new_dates = set(row_pay_data[0].flatten()) - all_maturities

        if new_dates:
          if OLS:
            df_clean = df_payoff.loc[(df_payoff != 0).any(axis=1),
                                         (df_payoff != 0).any(axis=0)]
            print("\u2705 DataFrame Complete (Exited Early)!")
            return df_clean
          else:
            # "\u2705 FIX: Add new dates to our master set and reindex
            all_maturities.update(new_dates)
            df_payoff = df_payoff.reindex(columns=sorted(all_maturities), fill_value=0.0)
 
        #    fill up the columns
        df_payoff.loc[index, row_pay_data[0]] = row_pay_data[1]
         # update the progress bar
        progress_ui.update(HTML(status_box(index + 1, total_rows)))
    # re-sort the columns so dates are chronological
    df_payoff = df_payoff.reindex(sorted(df_payoff.columns), axis=1)
    progress_ui.update(HTML("""
        <div style="font-family: Arial, sans-serif; padding: 10px 15px; background-color: #e6f4ea; 
                    border-left: 4px solid #34a853; border-radius: 4px; width: fit-content; color: #137333;">
            <b>"\u2705 DataFrame Complete!</b> All bonds added successfully.
            </div>
            """))
    return df_payoff

def ns_spot_rates(interim_estimates, mat_years, sofr_rate=None, fixed_tau=0.731):
    """
    Calculates spot rates using a fully vectorized Nelson-Siegel model.
    Accepts either single parameter vectors or (N, columns) simulation matrices.
    Dynamically accommodates tau if included in the estimates.
    """
    # 1. Ensure mat_years is a numpy array and handle division-by-zero
    t = np.array(mat_years, dtype=float)
    t = np.where(t == 0, 1e-8, t)
    
    if isinstance(interim_estimates, pd.DataFrame):
        interim_estimates = interim_estimates.to_numpy()
        
    # 2. Check if we are passing a 2D matrix of simulations
    is_matrix = isinstance(interim_estimates, np.ndarray) and interim_estimates.ndim == 2
    
    if sofr_rate is not None:  # Restricted model
        if is_matrix:
            # Base restricted params: b0, b2 (2 columns)
            b_0 = interim_estimates[:, 0][:, np.newaxis]
            b_2 = interim_estimates[:, 1][:, np.newaxis]
            
            # If 3 columns, the 3rd is tau
            if interim_estimates.shape[1] == 3:
                tau = interim_estimates[:, 2][:, np.newaxis]
            else:
                tau = fixed_tau 
        else:
            # Fallback for 1D array
            b_0, b_2 = interim_estimates[0], interim_estimates[1]
            tau = interim_estimates[2] if len(interim_estimates) == 3 else fixed_tau

        # Vectorized math
        spot_rates = (
            b_0
            + (sofr_rate - b_0) * (1 - np.exp(-t/tau)) / (t/tau)
            + b_2 * ((1 - np.exp(-t/tau)) / (t/tau) - np.exp(-t/tau))
        )
        
    else:  # Unrestricted model
        if is_matrix:
            # Base unrestricted params: b0, b1, b2 (3 columns)
            b_0 = interim_estimates[:, 0][:, np.newaxis]
            b_1 = interim_estimates[:, 1][:, np.newaxis]
            b_2 = interim_estimates[:, 2][:, np.newaxis]
            
            # If 4 columns, the 4th is tau (Index 3)
            if interim_estimates.shape[1] == 4:
                tau = interim_estimates[:, 3][:, np.newaxis]
            else:
                tau = fixed_tau            
        else:
            # Fallback for 1D array
            b_0, b_1, b_2 = interim_estimates[0], interim_estimates[1], interim_estimates[2]
            tau = interim_estimates[3] if len(interim_estimates) == 4 else fixed_tau

        # Vectorized math
        spot_rates = (
            b_0
            + b_1 * (1 - np.exp(-t/tau)) / (t/tau)
            + b_2 * ((1 - np.exp(-t/tau)) / (t/tau) - np.exp(-t/tau))
        )

    return spot_rates, t

def estimate_ns_parameters(df_payoff_matrix,P_actual,mat_years,guesses,sofr_rate=None):
  """
    Estimates Nelson-Siegel parameters by minimizing the Sum of Squared Residuals (SSR) 
    between actual bond prices and model-predicted bond prices.

    Args:
        df_payoff_matrix (pd.DataFrame or np.ndarray): Matrix of bond cash flows 
            where rows are bonds and columns represent time periods.
        P_actual (pd.Series or np.ndarray): Observed market prices of the bonds.
        mat_years (array-like): Time to maturity for each cash flow period, in years.
        guesses (list or array-like): Initial guesses for the optimization solver.
            Must have length 3 if sofr_rate is provided, or length 4 if None.
        sofr_rate (float, optional): A proxy short-term rate used to restrict the 
            short end of the curve. Defaults to None.

    Returns:
        scipy.optimize.OptimizeResult: The optimization result object containing 
            the estimated parameters (in the `.x` attribute), success status, 
            and minimum SSR achieved.

    Raises:
        ValueError: If the length of the `guesses` array does not match the 
            requirements of the chosen model type (restricted vs. unrestricted).
  """
  # objective function is sum squared residuals (SSR)
  def predict_prices(interim_estimates,df_payoff_matrix,P_actual,mat_years):

    # for step one get rates
    spot_rates,mat_years=ns_spot_rates(interim_estimates,mat_years,sofr_rate=sofr_rate)

    # calculate zero prices
    zero_prices=np.exp(-spot_rates*mat_years)

    # calculate predicted prices (@ here is the same as np.matmul)
    P_predicted=df_payoff_matrix@zero_prices

    # step 2 calculate the distance with sum of squared residuals
    ssr= np.sum((P_actual.values-P_predicted)**2)
    return ssr

  # use the scipy minimize function to estimate parameters

# Validate guess lengths based on model type
    if sofr_rate is not None and len(guesses) != 3:
        raise ValueError(f"Restricted model (SOFR={sofr_rate}) requires exactly 3 guesses. You provided {len(guesses)}.")
    
    if sofr_rate is None and len(guesses) != 4:
        raise ValueError(f"Unrestricted model requires exactly 4 guesses. You provided {len(guesses)}.")

  # Nelder-Mead doesn't take derivatives and tolerant of data
  method='Nelder-Mead'

  # minimize results
  ns_results=minimize(fun=predict_prices,
                  x0=guesses,
                  args=(df_payoff_matrix,P_actual,mat_years),
                  method=method)

  # get estimated coefficients of Nelson-Siegel


  # get status of minimization
  completion_status=ns_results.message

  if sofr_rate is not None:
    b_0,b_2,tau=ns_results.x
    display(f'Completion status: {completion_status}')
    display(f'Long Rate (Beta Zero) {b_0:.4f}..Slope (sofr_rate -Beta Zero) {sofr_rate-b_0: .4f}...\
    Shape (Beta Two) {b_2: .4f}...Scaling (Tau) {tau: .4f}') 

  else:
    b_0,b_1,b_2,tau=ns_results.x
    display(f'Completion status: {completion_status}')
    display(f'Long Rate (Beta Zero) {b_0:.4f}..Slope (Beta One) {b_1: .4f}...\
    Shape (Beta Two) {b_2: .4f}...Scaling (Tau) {tau: .4f}') 
  return ns_results

def calc_par_yield(months_to_maturity, interim_estimates, sofr_rate=None, freq=6, forward_start_months=0):
    """
    Calculates spot or forward par yields.
    
    Args:
        months_to_maturity (int/float): Tenor in months. Must be an int if >= freq.
        interim_estimates (list): Nelson-Siegel parameters.
        sofr_rate (float, optional): Short rate for restricted model.
        freq (int, optional): Payment frequency in months. Defaults to 6.
        forward_start_months (int/float, optional): Forward start period. Defaults to 0 (spot).
    """
    # 1. Guard against negative maturities
    if months_to_maturity < 0:
        raise ValueError(f"Maturity cannot be negative. Received: {months_to_maturity}")
        
    # 2. Type check: Enforce integers ONLY for swap-market maturities (>= freq)
    if months_to_maturity >= freq and not isinstance(months_to_maturity, int):
        raise TypeError(
            f"months_to_maturity must be an integer when >= freq ({freq} months). "
            f"Received: {type(months_to_maturity).__name__} ({months_to_maturity})"
        )
    
    # 3. Safeguard against exactly 0 maturity (estimates the immediate curve intercept)
    months_to_maturity = max(months_to_maturity, 0.0001)
    
    # 4. Generate schedule of relative months and accrual periods (gamma)
    if months_to_maturity < freq:
        # Short end: allows fractional months and single payments
        payment_months = [months_to_maturity]
        accrual_taus = [months_to_maturity / 12.0]
    else:
        # Short end: integer scheduling and sloppy stub handling
        full_periods = int(months_to_maturity // freq)
        payment_months = list(range(freq, (full_periods * freq) + 1, freq))
        accrual_taus = [freq / 12.0] * full_periods
        
        stub_months = months_to_maturity % freq
        if stub_months > 0:
            payment_months=[stub_months]+payment_months
            accrual_taus=[stub_months / 12.0]+accrual_taus            

    df = pd.DataFrame({
        'relative_months': payment_months,
        'tau': accrual_taus
    })
    
    # 5. Calculate Absolute Time (T) from TODAY (t=0)
    df['T_absolute'] = (df['relative_months'] + forward_start_months) / 12.0
    
    # 6. Get Spot Rates via your Nelson-Siegel function
    # if sofr_rate present check coeff
    if sofr_rate is not None and len(interim_estimates)>3:
      interim_estimates=list(interim_estimates)
      interim_estimates.pop(1)
    spot_rates, _ = ns_spot_rates(
        interim_estimates=interim_estimates, 
        mat_years=df['T_absolute'].values, 
        sofr_rate=sofr_rate
    )
    df['spot_rate'] = spot_rates
    
    # 7. Calculate Discount Factors back to today (t=0)
    df['DF'] = np.exp(-df['spot_rate'] * df['T_absolute'])
    
    # 8. Handle Forward Start Adjustment
    if forward_start_months > 0:
        T_start = forward_start_months / 12.0
        start_spot, _ = ns_spot_rates(interim_estimates, np.array([T_start]), sofr_rate)
        DF_start = np.exp(-start_spot[0] * T_start)
    else:
        DF_start = 1.0 
        
    # 9. Calculate Par Yield
    DF_N = df['DF'].iloc[-1]
    PV01 = (df['tau'] * df['DF']).sum()
    
    par_yield = (DF_start - DF_N) / PV01
    
    return par_yield

def calc_ytm(guesses, cash_flows, mat_years, prices):
    """
    Calculates the Yield to Maturity (YTM) using the Newton-Raphson method.
    """
    # FIX: Use np.isscalar to check if the user passed a single number instead of an array
    if np.isscalar(guesses):
        # If a single guess is provided, broadcast it to match the length of the prices array
        guesses = [guesses] * len(prices) 

    def ytm_objective(y, cash_flows, times, market_price):
        """Objective function: difference between modeled PV and actual price."""
        # Continuous compounding: PV = CF * e^(-y * t)
        pv = sum([cf * np.exp(-y * t) for cf, t in zip(cash_flows, times)])
        return pv - market_price

    def ytm_derivative(y, cash_flows, times, market_price):
        """Derivative of the objective function with respect to the yield (y)."""
        # Power rule applied to e^(-y * t) brings down the (-t)
        return sum([-t * cf * np.exp(-y * t) for cf, t in zip(cash_flows, times)])
    
    # Run the Newton-Raphson optimization
    # FIX: Updated x0 to 'guesses' and args to use 'mat_years'
    ytm = optimize.newton(
        func=ytm_objective,
        x0=guesses,
        fprime=ytm_derivative,
        args=(cash_flows, mat_years, prices)
    )
    
    return ytm

def calc_bond_metrics_2d(guesses, cash_flows, mat_years, prices):
    """
    Calculates YTM, Duration, and Convexity for a single bond OR a portfolio.
    Expects Cash Flows as (Dates x Bonds).
    """
    is_scalar_input = np.isscalar(prices)

    p = np.atleast_1d(prices)
    cf = np.asarray(cash_flows)

    # If a single bond's cash flows are passed as a flat list, stand it up into a column (Dates, 1)
    if cf.ndim == 1:
        cf = cf[:, np.newaxis]

    # Stand the dates up into a column: (Dates, 1)
    t = np.asarray(mat_years)[:, np.newaxis]

    if np.isscalar(guesses):
        guesses = np.full(len(p), guesses, dtype=float)
    else:
        guesses = np.atleast_1d(guesses)

    def ytm_objective(y, cf, t, p):
        # y is (8,). t is (100, 1). y * t automatically broadcasts to (100, 8)
        # Sum down the rows (axis=0) to collapse the dates, leaving (8,) PVs
        pv = np.sum(cf * np.exp(-y * t), axis=0)
        return pv - p

    def ytm_derivative(y, cf, t, p):
        return np.sum(-t * cf * np.exp(-y * t), axis=0)

    # --- STEP 1: Solve for YTM ---
    ytm = optimize.newton(
        func=ytm_objective,
        x0=guesses,
        fprime=ytm_derivative,
        args=(cf, t, p)
    )

    # --- STEP 2: Calculate Risk Metrics ---
    # ytm is (8,). t is (100, 1). discounted_cf becomes (100, 8)
    discounted_cf = cf * np.exp(-ytm * t)

    # Sum down the rows (axis=0) and divide by prices
    duration = np.sum(t * discounted_cf, axis=0) / p
    convexity = np.sum((t**2) * discounted_cf, axis=0) / p

    if is_scalar_input:
        return ytm[0], duration[0], convexity[0]

    return ytm, duration, convexity


def calc_bond_metrics_3d(guesses, cash_flows, mat_years, prices):
    """
    Calculates YTM, Duration, and Convexity for a matrix of prices (Scenarios x Bonds).
    Assumes continuous compounding.

    Returns:
        ytm (ndarray): Yield to Maturity
        duration (ndarray): Macaulay/Modified Duration
        convexity (ndarray): Convexity
    """
    cf = np.asarray(cash_flows)              # (100, 8)
    t = np.asarray(mat_years)[:, np.newaxis] # (100, 1)
    p = np.asarray(prices)                   # (6, 8)
    is_1d = False
    if p.ndim == 1:
        is_1d = True
        p = p[np.newaxis, :]  # Temporarily promote to (1, Bonds)
    # Broadcast the initial guess
    if np.isscalar(guesses):
        guesses = np.full_like(p, guesses, dtype=float)
    else:
        guesses = np.broadcast_to(guesses, p.shape)

    def ytm_objective(y, cf, t, p):
        # Insert the Dates dimension in the middle: (6, 1, 8)
        y_3d = y[:, np.newaxis, :]

        # Multiply to get (6, 100, 8), then sum across Dates (axis=1) -> (6, 8)
        pv = np.sum(cf * np.exp(-y_3d * t), axis=1)
        return pv - p

    def ytm_derivative(y, cf, t, p):
        y_3d = y[:, np.newaxis,:]
        return np.sum(-t * cf * np.exp(-y_3d * t), axis=1)

    # --- STEP 1: Solve for YTM ---
    ytm = optimize.newton(
        func=ytm_objective,
        x0=guesses,
        fprime=ytm_derivative,
        args=(cf, t, p)
    )

    # --- STEP 2: Calculate Risk Metrics ---
    # Convert the final YTM grid into 3D: (Scenarios, 8, 1)
    y_3d_final = ytm[:, np.newaxis,:]

    # Calculate the final discounted cash flows matrix: (Scenarios, 8, 100)
    discounted_cf = cf * np.exp(-y_3d_final * t)
    # Calculate Duration and Convexity
    # We divide directly by 'p' (the market prices) because the optimizer
    # just guaranteed that sum(discounted_cf) == p
    duration = np.sum(t * discounted_cf, axis=1) / p
    convexity = np.sum((t**2) * discounted_cf, axis=1) / p

    return ytm, duration, convexity


