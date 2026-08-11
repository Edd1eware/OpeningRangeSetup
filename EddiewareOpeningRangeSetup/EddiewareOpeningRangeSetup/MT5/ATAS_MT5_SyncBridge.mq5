#property copyright "Eddieware"
#property version   "1.00"
#property indicator_chart_window
#property indicator_plots 0

input string OutputFile = "ATAS_MT5_Sync\\mt5_price.csv";
input string HistoryFile = "ATAS_MT5_Sync\\mt5_m1_history.csv";
input int    PublishEveryMilliseconds = 100;
input int    PublishHistoryEverySeconds = 2;
input int    HistoryBars = 180;

ulong sequence = 0;
ulong last_history_publish_ms = 0;

int OnInit()
{
   int interval = MathMax(50, MathMin(1000, PublishEveryMilliseconds));
   if(!EventSetMillisecondTimer(interval))
   {
      Print("ATAS MT5 Sync Bridge: no se pudo iniciar el temporizador. Error=", GetLastError());
      return INIT_FAILED;
   }

   PublishQuote();
   PublishM1History();
   IndicatorSetString(INDICATOR_SHORTNAME, "ATAS MT5 Sync Bridge");
   Print("ATAS MT5 Sync Bridge activo: ", _Symbol, " -> FILE_COMMON\\", OutputFile);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("ATAS MT5 Sync Bridge detenido. reason=", reason);
}

void OnTimer()
{
   PublishQuote();

   ulong now_ms = GetTickCount64();
   if(now_ms - last_history_publish_ms >= (ulong)MathMax(1, PublishHistoryEverySeconds) * 1000)
   {
      PublishM1History();
      last_history_publish_ms = now_ms;
   }
}

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{
   return rates_total;
}

void PublishQuote()
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
      return;

   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   sequence++;

   string line = "ATAS_MT5_SYNC_V1;" + _Symbol + ";" +
                 DoubleToString(tick.bid, digits) + ";" +
                 DoubleToString(tick.ask, digits) + ";" +
                 DoubleToString(tick.last, digits) + ";" +
                 IntegerToString((long)tick.time_msc) + ";" +
                 IntegerToString((long)sequence) + ";" +
                 IntegerToString((long)TimeGMT() * 1000);

   ResetLastError();
   int handle = FileOpen(OutputFile,
                         FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON |
                         FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(handle == INVALID_HANDLE)
   {
      static datetime last_error_print = 0;
      datetime now = TimeLocal();
      if(now - last_error_print >= 10)
      {
         Print("ATAS MT5 Sync Bridge: FileOpen fallo. Error=", GetLastError());
         last_error_print = now;
      }
      return;
   }

   FileWriteString(handle, line);
   FileFlush(handle);
   FileClose(handle);
}

void PublishM1History()
{
   int requested = MathMax(30, MathMin(500, HistoryBars));
   MqlRates rates[];
   int copied = CopyRates(_Symbol, PERIOD_M1, 0, requested, rates);
   if(copied < 3)
      return;

   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   int server_gmt_offset_seconds = (int)(TimeTradeServer() - TimeGMT());

   ResetLastError();
   int handle = FileOpen(HistoryFile,
                         FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON |
                         FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(handle == INVALID_HANDLE)
   {
      Print("ATAS MT5 Sync Bridge: no se pudo escribir historial M1. Error=", GetLastError());
      return;
   }

   FileWriteString(handle,
      "ATAS_MT5_HISTORY_V1;" + _Symbol + ";" +
      IntegerToString(server_gmt_offset_seconds) + ";" +
      IntegerToString((long)sequence) + "\r\n");

   for(int index = 0; index < copied; index++)
   {
      long utc_seconds = (long)rates[index].time - server_gmt_offset_seconds;
      string row = IntegerToString(utc_seconds) + ";" +
                   DoubleToString(rates[index].open, digits) + ";" +
                   DoubleToString(rates[index].high, digits) + ";" +
                   DoubleToString(rates[index].low, digits) + ";" +
                   DoubleToString(rates[index].close, digits) + ";" +
                   IntegerToString(rates[index].tick_volume) + "\r\n";
      FileWriteString(handle, row);
   }

   FileFlush(handle);
   FileClose(handle);
}
