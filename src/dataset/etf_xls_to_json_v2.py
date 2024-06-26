import argparse
import json
import pandas as pd

def process_xls_file(file_path):
    # Read the XLSX file and select the "Main" tab
    df_results = pd.read_excel(file_path, sheet_name="Main")
    #print(df_results.columns)

    # Extract the required fields from the "Main" tab
    required_fields = ["Ticker", "BBG Ticker", "FIGI", "Name", "Description", "Type", "Domicile", "Tot Ret Ytd",
                       "Tot Ret 1Y", "Manager", "Fund Asset Class Focus", "Fund Asset Group", "Fund Industry Focus",
                       "Fund Geographical Focus", "Fund Objective", "Economic Association", "Fund Strategy",
                       "Fund Market Cap Focus", "Fund Style"]
    required_fields = [col.strip() for col in required_fields]
    data_results = rows_to_dic(xls_file_path=file_path, sheet_name="Main", fields=required_fields)
    data_results = df_results[required_fields].to_dict(orient="records")

    # Create a dictionary mapping ticker to summary data
    summary_fields = ["Name", "Ticker", "Class Assets (MLN USD)", "Fund Assets (MLN USD)", "Expense Ratio",
                      "Year-To-Date Return", "12Months Yield", "30Days Volatility", "Year-To-Date Flow", "1Month Flow", "1 Year NAV Tracking Error", "Holdings", "Primary", "Cross"]
    summary_data = rows_to_dic(xls_file_path=file_path, sheet_name="Summary", fields=summary_fields)

    # Create a dictionary mapping ticker to flow data
    flow_fields = ["Ticker", "Currency, Security", "OAS Effective Duration", "OAS Duration Coverage Ratio",
                      "YAS Modified Duration", "Options Available", "Payment Type"]
    flow_data = rows_to_dic(xls_file_path=file_path, sheet_name="Flow", fields=flow_fields)

    # Create a dictionary mapping ticker to expense data
    expense_fields = ["Ticker", "Expense Ratio", "Fund Manager Stated Fee", "Average Bid Ask Spread", "1 Year NAV Tracking Error", "Premium", "52Weeks Average Premium"]
    expense_data = rows_to_dic(xls_file_path=file_path, sheet_name="Expense", fields=expense_fields)

    # Create a dictionary mapping ticker to regulatory data
    regulatory_fields = ["Ticker", "Fund Type", "Structure", "Index Weight", "SFDR Class.", "Use Derivative", "Tax Form",
                      "NAIC", "UCITS", "UK Reporting", "SFC", "China", "Leverage", "Inception Date"]
    regulatory_data = rows_to_dic(xls_file_path=file_path, sheet_name="Regulatory", fields=regulatory_fields)

    # Create a dictionary mapping ticker to performance data
    performance_fields = ["Ticker", "Name", "1 Day Return", "Month-To-Date Return", "Year-To-Date Return", "1 Year Return", "3 Years Return",
                          "5 Years Return", "10 Years Return", "12 Months Yield"]
    performance_data = rows_to_dic(xls_file_path=file_path, sheet_name="Performance", fields=performance_fields)

    # Create a dictionary mapping ticker to liquidity data
    liquidity_fields = ["Ticker", "1 Day Volume", "Aggregated Volume", "Aggregated Value Traded", "Implied Liquidity",
                        "Bid Ask Spread", "Short Interest%", "Open Interest"]
    liquidity_data = rows_to_dic(xls_file_path=file_path, sheet_name="Liquidity", fields=liquidity_fields)

    # Create a dictionary mapping ticker to industry data
    industry_fields = ["Ticker", "Materials", "Communications", "Consumer Cyclical", "Consumer Non-Cyclical", "Diversified",
                       "Energy", "Financials", "Industrials", "Technology", "Utilities", "Government"]
    industry_data = rows_to_dic(xls_file_path=file_path, sheet_name="Industry", fields=industry_fields)

    # Create a dictionary mapping ticker to geography data
    geography_fields = ["Ticker", "N.Amer.", "LATAM", "West Euro", "APAC", "East Euro", "Africa/Middle East", "Central Asia"]
    geography_data = rows_to_dic(xls_file_path=file_path, sheet_name="Geography", fields=geography_fields)

    # Create a dictionary mapping ticker to descriptive data
    #descriptive_fields = ["Ticker", "Economic Association", "Name", "Tot Ret Ytd", "Fund Asset Class Focus",
                        #"Fund Strategy", "Fund Style", "General Attribute", "Local Objective", "Fund Objective",
                        #"Fund Industry Focus", "Fund Geographical Focus"]
    #descriptive_data = rows_to_dic(xls_file_path=file_path, sheet_name="Descriptive", fields=descriptive_fields)

    all_tickers = set(summary_data.keys()).union(
        flow_data.keys(),
        expense_data.keys(),
        regulatory_data.keys(),
        performance_data.keys(),
        liquidity_data.keys(),
        industry_data.keys(),
        geography_data.keys())

    # Merge the data from both tabs based on ticker
    for item in data_results:
        ticker_name = item["Ticker"]
        if isinstance(ticker_name, str):
            ticker = ticker_name.split(" ")[0]  # Extract the actual ticker
        else:
            ticker = str(ticker_name)  # Convert to string if not already # Extract the actual ticker
        item["Ticker"] = ticker
        item["ETFTickerName"] = ticker_name
        if ticker in all_tickers:
            add_data("Summary", ticker, summary_data, item)
            add_data("Flow", ticker, flow_data, item)
            add_data("Expense", ticker, expense_data, item)
            add_data("Regulatory", ticker, regulatory_data, item)
            add_data("Performance", ticker, performance_data, item)
            add_data("Liquidity", ticker, liquidity_data, item)
            add_data("Industry", ticker, industry_data, item)
            add_data("Geography", ticker, geography_data, item)
            'add_data("Descriptive", ticker, descriptive_data, item)'

    return data_results


def add_data(category_name, ticker, data, item):
    if ticker in data:
        item[category_name] = data[ticker].to_dict()
    else:
        print(f"Warning: Missing data for ticker: {ticker} in category/tab {category_name}")
        item[category_name] = {}


def rows_to_dic(xls_file_path, sheet_name, fields):
    df = pd.read_excel(xls_file_path, sheet_name=sheet_name)
    data = {}
    for _, row in df[fields].iterrows():
        if pd.isna(row["Ticker"]):
            print(f"Warning: Skipping row with missing Ticker: \n{row}")
            continue
        ticker = row["Ticker"].split(" ")[0]
        cleaned_row = row.apply(lambda x: "Not Available" if pd.isna(x) or x in ["N/A", "N.A.", "--", "nan", "NaN"] else x)
        cleaned_row = cleaned_row.apply(lambda x: "Not Applicable" if pd.isna(x) or x in ["#N/A Field Not Applicable"] else x)
        #cleaned_row = row.apply(lambda x: "not available" if pd.isna(x) or x in ["N/A", "N.A.", "--", "nan", "NaN", "#N/A Field Not Applicable"] else x)
        data[ticker] = cleaned_row
        del data[ticker]["Ticker"]

    return data


def save_to_json(data, output_file):
    with open(output_file, "w") as json_file:
        json.dump(data, json_file, indent=4)

def main():
    parser = argparse.ArgumentParser(description="Process XLS file and create JSON dataset")
    parser.add_argument("xls_file", help="Path to the input XLS file")
    parser.add_argument("output_file", help="Path to the output JSON file")
    args = parser.parse_args()

    data = process_xls_file(args.xls_file)
    save_to_json(data, args.output_file)

    print(f"JSON dataset created: {args.output_file}")

if __name__ == "__main__":
    main()