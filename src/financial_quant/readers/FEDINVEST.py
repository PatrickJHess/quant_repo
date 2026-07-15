import requests
from io import StringIO
import pandas as pd
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from financial_quant.quant_core.fixed_income import adjust_bond_pay_dates

def FEDInvest(price_date):
  """
    Fetches historical security prices from the FedInvest portal.


    Args:
        price_date (datetime.date): The date for which to retrieve prices.
            Note: Current day is typically available after 1:00 PM ET on business days.




    Returns:
        tuple: (pandas.DataFrame, str) if successful. The DataFrame contains
               security details (CUSIP, Price, Yield), and the string is the
               official "Prices For" date stamp from the site.
        tuple: (str, None) if the request fails or no data is found for the date
                (attempt to fetch current day before 1:00 PM ET).


    Example:
        >>> from datetime import date
        >>> df, stamp = FEDInvest(date(2025, 3, 17))
  """


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


  price_date=make_date(price_date)
  # make share date of prices and settlement date are settlement dates
  price_date=adjust_bond_pay_dates(price_date)[0]
  if price_date > date.today():
    return "price_date is in the future", None, None


  settlement_date=price_date+relativedelta(days=1)
  settlement_date=adjust_bond_pay_dates(settlement_date)


  # URL address of Treasury Direct Select A Date
  url = "https://treasurydirect.gov/GA-FI/FedInvest/selectSecurityPriceDate"


  # Standard headers to look like a real browser
  headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\
     (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded"
  }
  #  variable names and type identified from inspecting url
  month=str(price_date.month)
  day=str(price_date.day)
  year=str(price_date.year)


  # payload passed in request post
  payload={'priceDate.month':month,
           'priceDate.day':day,
           'priceDate.year':year,
           "submit": "Show Prices"}


  # fires off form and returns prices for date
  try:
        response = requests.post(url, data=payload, headers=headers, timeout=10)
        response.raise_for_status()
  except requests.exceptions.RequestException as e:
        return f"Connection Error: {e}", None


  # reads the html
  # Pandas recommends to wrap the response in StingIO to make file like
  tables=pd.read_html(StringIO(response.text),match='CUSIP')


  # from inspection there is a single table
  df=tables[0]


  df['MATURITY DATE']=pd.to_datetime(df['MATURITY DATE'])


  # drop rows equal to or less than settlement date
  df_filtered=df[df['MATURITY DATE']>pd.to_datetime(settlement_date[0])]


  return df_filtered, price_date,settlement_date[0]

def clean_FEDInvest(df):


    import pandas as pd
    # Filters for Standard Securities
    keep_rows=df['SECURITY TYPE'].str.contains('bill|note|bond',case=False)
    security_df=df[keep_rows].copy()
 
    # Removes Clutter
    drop_columns=['CUSIP','CALL DATE']
    security_df.drop(columns=drop_columns,inplace=True)


    # Creates a Time-Series Index
    security_df.set_index('MATURITY DATE',inplace=True)
    security_df.index=pd.to_datetime(security_df.index)
    security_df.sort_index(inplace=True)


    # Standardizes Financial Terms
    change_column_names={'RATE':'Coupon',
                         'BUY':'Price Ask',
                         'SELL':'Price Bid'}
    security_df.rename(columns=change_column_names,inplace=True)


    # Formats Numeric Data
    numeric_cols = ['Coupon', 'Price Ask', 'Price Bid', 'YIELD']
    for col in numeric_cols:
        if col in security_df.columns:
            security_df[col] = security_df[col].astype(str).str.replace('%', '', regex=False).astype(float)


    return security_df



