from configparser import ConfigParser
from datetime import datetime, timedelta
import json
import csv
import traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class T212Exporter():
    baseRestUrl = "https://live.trading212.com/rest/history"

    def __init__(self):
        self.config = ConfigParser()
        self.config.read("config.ini")
        self.transactions = []

    def run(self):
        try:
            self.setUp()
            self.login()
            self.exportTransactions()
            print("Total of {} transactions".format(len(self.transactions)))

            # Write transactions to json
            with open(self.config['Trading212']['OutputFile'], 'w', encoding='utf-8') as f:
                json.dump(self.transactions, f, ensure_ascii=False, indent=4)
        finally:
            self.tearDown()

    def setUp(self):
        self.browser = webdriver.Chrome("./driver/chromedriver")
    
    def login(self):
        print("Logging in...")    
        self.browser.get("https://www.trading212.com/en/login")
        emailEl = self.browser.find_element(By.XPATH, "/html/body/div[1]/section[2]/div/div/div/form/div[2]/div[1]/input")
        paswdEl = self.browser.find_element(By.XPATH, "/html/body/div[1]/section[2]/div/div/div/form/div[2]/div[2]/input[1]")
        loginEl = self.browser.find_element(By.XPATH, "/html/body/div[1]/section[2]/div/div/div/form/input[6]")

        emailEl.send_keys(self.config['Trading212']['Email'])
        paswdEl.send_keys(self.config['Trading212']['Password'])
        loginEl.click()

        try:
            continueEl = WebDriverWait(self.browser, 60).until(
                EC.presence_of_element_located((By.XPATH, "/html/body/div[6]/div[3]/div[2]/div"))
            )
            continueEl.click()
        except Exception as e:
            print("Error while waiting for login to finish")
            print("Will attempt to fetch transactions")

    def exportTransactions(self):
        print("Fetching transactions...")
        startTime = datetime.fromisoformat(self.config['Trading212']['StartDate'])
        endTime = datetime.fromisoformat(self.config['Trading212']['EndDate'])

        delta = timedelta(days = 1)
        while startTime <= endTime:
            # We fetch 10 days at a time
            self.fetchTransactions(startTime, startTime + delta)
            startTime += delta

    def fetchTransactions(self, startTime, endTime):
        startTimeStr = startTime.isoformat() + 'Z'
        endTimeStr = endTime.isoformat() + 'Z'

        url = self.baseRestUrl + "/all?newerThan={}&olderThan={}".format(startTimeStr, endTimeStr)

        transactions = self.fetchApiData(url)["data"]
        print("{} to {} - {} transactions".format(startTime, endTime, len(transactions)))

        for transaction in transactions:
            try: 
                self.processTransaction(transaction)
            except Exception as e:
                traceback.print_exc()
                print("Failed to process transaction")
                print(transaction)

    def processTransaction(self, transaction):
        key = transaction["heading"]["key"]

        if key == "history.instrument":
            subKey = transaction["subHeading"]["key"]

            if subKey == "history.order.filled.buy":
                self.fetchTransactionDetails(transaction, "buy")
            elif subKey == "history.order.filled.sell":
                self.fetchTransactionDetails(transaction, "sell")
            elif subKey in ["history.order.buy", "history.order.sell"]:
                pass
            else:
                print("    Unknown transaction type {}. Skipping it".format(subKey))

    def fetchTransactionDetails(self, transaction, orderType):
        url = self.baseRestUrl + transaction["detailsPath"]
        transaction = self.fetchApiData(url)

        prettyName = transaction["heading"]["context"]["prettyName"]
        symbol = transaction["heading"]["context"]["instrument"]
        tradeDate = self.findValue(transaction, "history.details.order.fill.date-executed.key")["date"]
        quantity = self.findValue(transaction, "history.details.order.fill.quantity.key")["quantity"]
        price = self.findValue(transaction, "history.details.order.fill.price.key")["amount"]
        currency = self.findValue(transaction, "history.details.order.fill.price.key")["currency"]

        self.transactions.append({
                "prettyName": prettyName,
                "symbol": symbol,
                "tradeDate": tradeDate,
                "price": price,
                "quantity": quantity,
                "currency": currency,
                "orderType": orderType
            })

    # Finds the value of a key in the transaction details API response
    def findValue(self, transaction, key):
        for item in transaction["sections"]:
            if "description" in item and item["description"]["key"] == key:
                return item["value"]["context"]

            elif "rows" in item:
                for row in item["rows"]:
                    if "description" in row and row["description"]["key"] == key:
                        return row["value"]["context"]
        raise Exception("Key: `{}` not found in transaction details".format(key))

    def fetchApiData(self, url):
        self.browser.get(url)
        return json.loads(self.browser.find_element_by_tag_name('pre').text)


    def tearDown(self):
        self.browser.close()


class YahooFinanceImporter():
    SymbolMap = {
        "BTCE": "DE000A27Z304.SG",
        "WDI": "WDI.DE",
        "ECAR": "ECAR.L"
    }

    def __init__(self):
        self.config = ConfigParser()
        self.config.read("config.ini")
        self.transactions = json.load(open(self.config['Trading212']['OutputFile'],)) 

    def writeCsv(self):
        print("Writing transactions to CSV...")
        with open(self.config['YahooFinance']['OutputFile'], 'w', newline='') as csvfile:
            fieldnames = [
                "Symbol",
                "Current Price",
                "Date",
                "Time",
                "Change",
                "Open",
                "High",
                "Low",
                "Volume",
                "Trade Date",
                "Purchase Price",
                "Quantity",
                "Commission",
                "High Limit",
                "Low Limit",
                "Comment"
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for transaction in self.transactions:
                if transaction["orderType"] == "sell":
                    quantity = -transaction["quantity"]
                else:
                    quantity = transaction["quantity"]

                symbol = transaction["symbol"]
                if symbol in self.SymbolMap:
                    symbol = self.SymbolMap[symbol]
                elif transaction["currency"] == "GBX":
                    # UK stocks are typically mapped with .L at end
                    symbol = transaction["symbol"] + ".L"
                elif transaction["currency"] == "USD":
                    # Dollar stocks typically don't need any extra work
                    pass
                else:
                    print("Unknown symbol {}".format(symbol))

                tradeDate = datetime.fromisoformat(transaction["tradeDate"])

                writer.writerow({
                    "Symbol": symbol,
                    "Date": tradeDate.strftime("%Y/%m/%d"),
                    "Time": tradeDate.strftime("%H:%M %Z"),
                    "Trade Date": tradeDate.strftime("%Y%m%d"),
                    "Purchase Price": transaction["price"],
                    "Quantity": quantity
                })


if __name__ == '__main__':
    exporter = T212Exporter()
    exporter.run()

    importer = YahooFinanceImporter()
    importer.writeCsv()

    print("All done!")
    print("----------------------------------------------------------")
    print("              Star the repo to show support               ")
    print(" https://github.com/praveendath92/Trading212-CSV-Exporter ")
    print("----------------------------------------------------------")

