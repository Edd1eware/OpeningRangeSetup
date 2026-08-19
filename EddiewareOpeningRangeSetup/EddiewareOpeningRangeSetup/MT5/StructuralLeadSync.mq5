//+------------------------------------------------------------------+
//| StructuralLeadSync.mq5                                           |
//| Quien lidera a quien, por ESTRUCTURA (pivotes de swing).          |
//|                                                                  |
//| Port del indicador ATAS 13_NQ_ES_SyncMonitor. A diferencia de     |
//| ATAS, MQL5 puede leer un segundo simbolo con CopyRates, asi que   |
//| no hace falta puente de archivos.                                 |
//|                                                                  |
//| Metodo: se busca el ultimo pivote confirmado del simbolo A y el   |
//| pivote del MISMO tipo en B. El que lo imprimio antes lidera, y    |
//| el desfase se mide en velas. No se comparan precios, solo el      |
//| orden temporal de la estructura, asi que no hace falta convertir  |
//| escalas entre instrumentos.                                       |
//|                                                                  |
//| Solo lectura: no coloca ordenes ni escribe archivos.              |
//+------------------------------------------------------------------+
#property copyright "Eddieware"
#property version   "1.00"
#property indicator_chart_window
#property indicator_plots 0

input string           SymbolB              = "SPY.NYSE-24"; // Segundo simbolo (A = el del grafico)
input string           DisplayNameA         = "NQ";        // Nombre a mostrar del simbolo del grafico
input string           DisplayNameB         = "SP500";     // Nombre a mostrar del segundo simbolo
input ENUM_TIMEFRAMES  WorkTimeframe        = PERIOD_M1;  // Timeframe de analisis
input int              HistoryBars          = 240;        // Velas de historia a leer
input int              PivotStrength        = 2;          // Fuerza del pivote (velas a cada lado)
input int              PivotSwingLookback   = 20;         // Ventana para medir el swing (velas)
input int              MinLeadCandles       = 3;          // Desfase minimo para declarar lider
input int              MaxLeadCandles       = 8;          // Desfase maximo aceptado como relacion
input int              MinimumCandles       = 24;         // Velas minimas para analizar
input double           MinPivotSwingAtr     = 5.0;        // Swing minimo del pivote (en ATR)
input int              AtrPeriod            = 14;
input int              StaleAfterSeconds    = 3;          // Feed vencido despues de N segundos
input bool             MuteBeforeWeekStart  = true;       // Sin veredicto hasta el inicio de semana
input int              WeekStartHourNy      = 9;          // Inicio de semana: hora NY
input int              WeekStartMinuteNy    = 30;         // Inicio de semana: minuto NY
input int              NyGmtOffsetHours     = -4;         // NY respecto a GMT (-4 EDT, -5 EST)
input color            LeadColor            = clrDeepSkyBlue;
input color            SyncColor            = clrLimeGreen;
input color            ProblemColor         = clrOrangeRed;
input color            WaitColor            = clrGold;
input int              FontSize             = 11;
input bool             CenterText           = true;       // Centrar el texto en el grafico
input int              TextYOffset          = 44;         // Altura del bloque (deja sitio arriba)
input bool             AutoFitText          = true;       // Encoger la fuente si no cabe (mosaico)
input int              MinFontSize          = 6;          // Fuente minima al encoger
input bool             EnableTelegram       = true;       // Avisar por Telegram al detectar desfase
input string           CredentialsFile      = "telegram_credentials.txt"; // En Common\Files
input int              TelegramCooldownSecs = 300;         // Minimo entre avisos
input bool             SendScreenshot       = true;        // Adjuntar captura del grafico
input int              ScreenshotWidth      = 0;           // 0 = ancho actual del grafico
input int              ScreenshotHeight     = 0;           // 0 = alto actual del grafico

#define PREFIX  "SLS_"
#define LBL_MAIN   PREFIX "main"
#define LBL_DETAIL PREFIX "detail"
#define LBL_DATA   PREFIX "data"
#define SCREENSHOT_FILE "StructuralLeadSync_shot.png"

string symbol_a = "";

string   last_alert_signature = "";
datetime last_alert_time      = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   symbol_a = _Symbol;

   // Comparar un simbolo consigo mismo siempre da "EN SINCRONIA": no es un
   // resultado, es el indicador puesto en el grafico equivocado.
   if(SymbolB == symbol_a)
   {
      Print("StructuralLeadSync: SymbolB (", SymbolB, ") es el simbolo del grafico. ",
            "Ponlo en el otro instrumento o cambia SymbolB.");
      return INIT_FAILED;
   }

   if(!SymbolSelect(SymbolB, true))
   {
      Print("StructuralLeadSync: no se pudo seleccionar ", SymbolB,
            ". Agregalo al Market Watch. Error=", GetLastError());
      return INIT_FAILED;
   }

   IndicatorSetString(INDICATOR_SHORTNAME, "Structural Lead Sync");
   EventSetTimer(1);
   Evaluate();
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   ObjectsDeleteAll(0, PREFIX);
   ChartRedraw();
}

//+------------------------------------------------------------------+
void OnTimer()
{
   Evaluate();
}

//+------------------------------------------------------------------+
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

//+------------------------------------------------------------------+
void Evaluate()
{
   MqlRates a[], b[];
   int bars = MathMax(MinimumCandles + PivotStrength * 2 + AtrPeriod, HistoryBars);

   int got_a = CopyRates(symbol_a, WorkTimeframe, 0, bars, a);
   int got_b = CopyRates(SymbolB,  WorkTimeframe, 0, bars, b);

   bool a_ok = FeedIsFresh(symbol_a);
   bool b_ok = FeedIsFresh(SymbolB);

   // Siempre se nombran los dos lados: un feed viejo no debe confundirse con
   // una caida total, y una caida doble no debe ocultar la mitad.
   if(!a_ok || !b_ok)
   {
      string status = "";
      if(!a_ok && !b_ok)      status = NameA() + " SIN DATOS | " + NameB() + " SIN DATOS";
      else if(!a_ok)          status = NameA() + " SIN DATOS | " + NameB() + " FEED OK";
      else                    status = NameB() + " SIN DATOS | " + NameA() + " FEED OK";

      Show(status, "Ultimo tick: " + NameA() + "=" + AgeText(symbol_a) + " | " + NameB() + "=" + AgeText(SymbolB),
           DataLine(got_a, got_b), ProblemColor);
      return;
   }

   if(got_a < MinimumCandles || got_b < MinimumCandles)
   {
      Show("CARGANDO ESTRUCTURA", "Velas insuficientes en " + EnumToString(WorkTimeframe),
           DataLine(got_a, got_b), WaitColor);
      return;
   }

   // Antes de la apertura semanal ningun lado puede liderar legitimamente:
   // se retiene el veredicto en lugar de reportar ruido como estructura.
   if(IsBeforeWeekStart())
   {
      Show("SEMANA NO INICIADA",
           StringFormat("%s abre lunes %02d:%02d NY: sin veredicto de liderazgo",
                        NameB(), WeekStartHourNy, WeekStartMinuteNy),
           DataLine(got_a, got_b), WaitColor);
      return;
   }

   datetime pivot_a = 0;
   int      kind_a  = 0;   // +1 = maximo, -1 = minimo
   if(!FindLastPivot(a, got_a, pivot_a, kind_a))
   {
      Show("SIN PIVOTE CONFIRMADO", "No hay swing >= " + DoubleToString(MinPivotSwingAtr, 1) + " ATR en " + NameA(),
           DataLine(got_a, got_b), WaitColor);
      return;
   }

   datetime pivot_b = 0;
   if(!FindPairedPivot(b, got_b, kind_a, pivot_a, MaxLeadCandles, pivot_b))
   {
      // Uno marco estructura y el otro no la acompano: el que la imprimio va
      // adelante. El detalle aclara que el seguimiento todavia no ocurre, para
      // no confundirlo con un desfase ya medido entre dos pivotes reales.
      Show(NameA() + " LIDERA",
           StringFormat("Pivote %s en %s a las %s; %s aun no marca equivalente en +-%d velas",
                        KindText(kind_a), NameA(), TimeToString(pivot_a, TIME_MINUTES),
                        NameB(), MaxLeadCandles),
           DataLine(got_a, got_b), LeadColor);

      MaybeNotify(NameA() + " LIDERA", "Sin seguimiento de " + NameB(),
                  DataLine(got_a, got_b), pivot_a, 0);
      return;
   }

   int period_seconds = PeriodSeconds(WorkTimeframe);
   if(period_seconds <= 0)
      return;

   // Positivo = el pivote de B llego despues, o sea A lidera.
   int lag = (int)((pivot_b - pivot_a) / period_seconds);

   string status, detail;
   color  paint;

   if(lag >= MinLeadCandles)
   {
      status = NameA() + " LIDERA";
      detail = StringFormat("Pivote %s: %s adelanta %d velas a %s",
                            KindText(kind_a), NameA(), lag, NameB());
      paint  = LeadColor;
   }
   else if(lag <= -MinLeadCandles)
   {
      status = NameB() + " LIDERA";
      detail = StringFormat("Pivote %s: %s adelanta %d velas a %s",
                            KindText(kind_a), NameB(), -lag, NameA());
      paint  = LeadColor;
   }
   else
   {
      status = "EN SINCRONIA";
      detail = StringFormat("Pivote %s simultaneo (desfase %d velas, minimo %d)",
                            KindText(kind_a), lag, MinLeadCandles);
      paint  = SyncColor;
   }

   string data = StringFormat("%s pivote %s  |  %s pivote %s  |  %s",
                              NameA(), TimeToString(pivot_a, TIME_MINUTES),
                              NameB(), TimeToString(pivot_b, TIME_MINUTES),
                              DataLine(got_a, got_b));

   Show(status, detail, data, paint);

   // Solo el desfase (liderazgo) se avisa: sincronia y estados de espera no.
   // Este es el caso con desfase medido entre dos pivotes, asi que lleva captura.
   if(MathAbs(lag) >= MinLeadCandles)
      MaybeNotify(status, detail, data, pivot_a, pivot_b, true);
}

//+------------------------------------------------------------------+
//| Pivote fractal: el maximo (o minimo) mas reciente que domina a    |
//| PivotStrength velas de cada lado y cuyo swing supera el filtro     |
//| de ATR. El indice arranca en PivotStrength para no usar velas sin  |
//| confirmar a la derecha, que es lo que haria la senal no causal.    |
//+------------------------------------------------------------------+
bool FindLastPivot(const MqlRates &r[], const int count, datetime &pivot_time, int &kind)
{
   double atr = Atr(r, count);
   if(atr <= 0.0)
      return false;

   double min_swing = atr * MinPivotSwingAtr;

   for(int i = count - 1 - PivotStrength; i >= PivotStrength; i--)
   {
      if(IsPivot(r, count, i, +1, min_swing)) { pivot_time = r[i].time; kind = +1; return true; }
      if(IsPivot(r, count, i, -1, min_swing)) { pivot_time = r[i].time; kind = -1; return true; }
   }
   return false;
}

//+------------------------------------------------------------------+
//+------------------------------------------------------------------+
//| Empareja con el pivote del MISMO tipo mas cercano en el tiempo al  |
//| de referencia, dentro de la ventana de desfase permitida. Tomar    |
//| simplemente el pivote mas reciente emparejaria swings distintos:   |
//| si un lado marco hace 5 min y el otro hace 40, el desfase medido   |
//| no describe ninguna relacion real entre las dos estructuras.       |
//+------------------------------------------------------------------+
bool FindPairedPivot(const MqlRates &r[], const int count, const int kind,
                     const datetime anchor, const int max_lag_bars, datetime &pivot_time)
{
   double atr = Atr(r, count);
   if(atr <= 0.0)
      return false;

   double min_swing = atr * MinPivotSwingAtr;
   int    period_seconds = PeriodSeconds(WorkTimeframe);
   if(period_seconds <= 0)
      return false;

   bool found = false;
   int  best_abs_lag = 0;

   for(int i = count - 1 - PivotStrength; i >= PivotStrength; i--)
   {
      if(!IsPivot(r, count, i, kind, min_swing))
         continue;

      int lag = (int)((r[i].time - anchor) / period_seconds);
      int abs_lag = MathAbs(lag);
      if(abs_lag > max_lag_bars)
         continue;

      if(!found || abs_lag < best_abs_lag)
      {
         found = true;
         best_abs_lag = abs_lag;
         pivot_time = r[i].time;
      }
   }
   return found;
}

//+------------------------------------------------------------------+
bool IsPivot(const MqlRates &r[], const int count, const int i, const int kind, const double min_swing)
{
   if(i - PivotStrength < 0 || i + PivotStrength >= count)
      return false;

   // La fuerza confirma el pivote (±PivotStrength velas), pero el swing se mide
   // sobre una ventana mucho mas amplia. Medirlo solo en las 5 velas del entorno
   // haria inalcanzable un umbral de varios ATR y casi nada calificaria.
   int from = MathMax(0, i - PivotSwingLookback);
   int to   = MathMin(count - 1, i + PivotStrength);

   if(kind > 0)
   {
      double peak = r[i].high;
      for(int k = 1; k <= PivotStrength; k++)
         if(r[i - k].high >= peak || r[i + k].high >= peak)
            return false;

      double lowest = r[i].low;
      for(int j = from; j <= to; j++)
         if(r[j].low < lowest) lowest = r[j].low;

      return (peak - lowest) >= min_swing;
   }

   double trough = r[i].low;
   for(int k = 1; k <= PivotStrength; k++)
      if(r[i - k].low <= trough || r[i + k].low <= trough)
         return false;

   double highest = r[i].high;
   for(int j = from; j <= to; j++)
      if(r[j].high > highest) highest = r[j].high;

   return (highest - trough) >= min_swing;
}

//+------------------------------------------------------------------+
double Atr(const MqlRates &r[], const int count)
{
   int n = MathMin(MathMax(2, AtrPeriod), count - 1);
   if(n < 2)
      return 0.0;

   double sum = 0.0;
   for(int i = count - n; i < count; i++)
   {
      double tr = MathMax(r[i].high - r[i].low,
                  MathMax(MathAbs(r[i].high - r[i - 1].close),
                          MathAbs(r[i].low  - r[i - 1].close)));
      sum += tr;
   }
   return sum / n;
}

//+------------------------------------------------------------------+
bool FeedIsFresh(const string sym)
{
   MqlTick t;
   if(!SymbolInfoTick(sym, t))
      return false;

   return (TimeCurrent() - t.time) <= MathMax(1, StaleAfterSeconds);
}

//+------------------------------------------------------------------+
string AgeText(const string sym)
{
   MqlTick t;
   if(!SymbolInfoTick(sym, t))
      return "n/d";

   return IntegerToString((int)(TimeCurrent() - t.time)) + "s";
}

//+------------------------------------------------------------------+
//| El servidor de IC Markets no corre en hora NY, asi que la hora de  |
//| NY se deriva de GMT con el offset configurable (EDT -4 / EST -5).   |
//+------------------------------------------------------------------+
bool IsBeforeWeekStart()
{
   if(!MuteBeforeWeekStart)
      return false;

   datetime ny = TimeGMT() + NyGmtOffsetHours * 3600;
   MqlDateTime d;
   TimeToStruct(ny, d);

   if(d.day_of_week == 0)   // domingo
      return true;

   if(d.day_of_week == 1)   // lunes antes de la apertura
      return (d.hour * 60 + d.min) < (WeekStartHourNy * 60 + WeekStartMinuteNy);

   return false;
}

//+------------------------------------------------------------------+
string KindText(const int kind) { return kind > 0 ? "SUPERIOR" : "INFERIOR"; }

//+------------------------------------------------------------------+
//| Nombres para pantalla: el ticker del broker (USTEC, SPY.NYSE-24)   |
//| no es como el usuario piensa los instrumentos (NQ, SP500).         |
//+------------------------------------------------------------------+
string NameA() { return StringLen(DisplayNameA) > 0 ? DisplayNameA : symbol_a; }
string NameB() { return StringLen(DisplayNameB) > 0 ? DisplayNameB : SymbolB;  }

//+------------------------------------------------------------------+
string DataLine(const int got_a, const int got_b)
{
   return StringFormat("velas %s=%d %s=%d", NameA(), got_a, NameB(), got_b);
}

//+------------------------------------------------------------------+
void Show(const string status, const string detail, const string data, const color paint)
{
   string main = "ESTADO " + NameA() + "/" + NameB() + " | " + status;

   // En mosaico el grafico es angosto y el texto se sale o se encima con otros
   // indicadores. Se busca el mayor recorte de fuente con el que las TRES lineas
   // caben, y se aplica el mismo a todas para que el bloque quede parejo.
   int drop = FitDrop(main, detail, data);
   int main_size  = MathMax(MinFontSize, FontSize + 3 - drop);
   int other_size = MathMax(MinFontSize, FontSize - drop);

   // El interlineado sale del tamano ya ajustado: fijarlo en pixeles haria que las
   // lineas se encimaran entre si en cuanto cambiara la fuente.
   int top     = MathMax(0, TextYOffset);
   int spacing = other_size + 9;

   Label(LBL_MAIN,   top,                   main,   paint,     main_size);
   Label(LBL_DETAIL, top + spacing + 3,     detail, clrWhite,  other_size);
   Label(LBL_DATA,   top + spacing * 2 + 3, data,   clrSilver, other_size);
   ChartRedraw();
}

//+------------------------------------------------------------------+
//+------------------------------------------------------------------+
//| Un mismo desfase se reporta una sola vez: la firma incluye los     |
//| dos pivotes, asi que un aviso nuevo exige estructura nueva y no    |
//| solo que el timer haya vuelto a correr.                            |
//+------------------------------------------------------------------+
void MaybeNotify(const string status, const string detail, const string data,
                 const datetime pivot_a, const datetime pivot_b, const bool with_photo = false)
{
   if(!EnableTelegram)
      return;

   string signature = StringFormat("%s|%s|%s", status,
                                   TimeToString(pivot_a, TIME_DATE | TIME_MINUTES),
                                   TimeToString(pivot_b, TIME_DATE | TIME_MINUTES));

   if(signature == last_alert_signature)
      return;

   if(last_alert_time > 0 && (TimeCurrent() - last_alert_time) < MathMax(0, TelegramCooldownSecs))
      return;

   string token = "", chat_id = "";
   if(!ReadCredentials(token, chat_id))
   {
      Print("StructuralLeadSync: no se pudieron leer credenciales de ", CredentialsFile,
            " en Common\\Files");
      return;
   }

   string text = StringFormat("%s\n%s\n%s\n%s %s",
                              status, detail, data,
                              NameA(), TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES));

   // La captura solo acompana un desfase ya medido entre dos pivotes reales.
   // Si falla, el aviso igual sale como texto: perder el mensaje por no poder
   // guardar un PNG seria peor que mandarlo sin imagen.
   bool sent = false;
   if(with_photo && SendScreenshot && CaptureChart())
      sent = SendTelegramPhoto(token, chat_id, text, SCREENSHOT_FILE);

   if(!sent)
      sent = SendTelegram(token, chat_id, text);

   if(sent)
   {
      last_alert_signature = signature;
      last_alert_time      = TimeCurrent();
      Print("StructuralLeadSync: aviso enviado -> ", status);
   }
}

//+------------------------------------------------------------------+
bool CaptureChart()
{
   int w = ScreenshotWidth  > 0 ? ScreenshotWidth  : (int)ChartGetInteger(0, CHART_WIDTH_IN_PIXELS);
   int h = ScreenshotHeight > 0 ? ScreenshotHeight : (int)ChartGetInteger(0, CHART_HEIGHT_IN_PIXELS);
   if(w <= 0 || h <= 0)
      return false;

   if(!ChartScreenShot(0, SCREENSHOT_FILE, w, h, ALIGN_RIGHT))
   {
      Print("StructuralLeadSync: ChartScreenShot fallo. Error=", GetLastError());
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| sendPhoto exige multipart/form-data, que MQL5 no arma solo: hay    |
//| que concatenar cabecera de texto + bytes del PNG + cierre.         |
//+------------------------------------------------------------------+
bool SendTelegramPhoto(const string token, const string chat_id,
                       const string caption, const string file_name)
{
   uchar image[];
   int fh = FileOpen(file_name, FILE_READ | FILE_BIN);
   if(fh == INVALID_HANDLE)
   {
      Print("StructuralLeadSync: no se pudo abrir la captura. Error=", GetLastError());
      return false;
   }
   int image_size = (int)FileSize(fh);
   if(image_size <= 0)
   {
      FileClose(fh);
      return false;
   }
   ArrayResize(image, image_size);
   FileReadArray(fh, image, 0, image_size);
   FileClose(fh);

   string boundary = "----MQL5Boundary" + IntegerToString(GetTickCount());

   string head = "--" + boundary + "\r\n"
               + "Content-Disposition: form-data; name=\"chat_id\"\r\n\r\n" + chat_id + "\r\n"
               + "--" + boundary + "\r\n"
               + "Content-Disposition: form-data; name=\"caption\"\r\n\r\n" + caption + "\r\n"
               + "--" + boundary + "\r\n"
               + "Content-Disposition: form-data; name=\"photo\"; filename=\"chart.png\"\r\n"
               + "Content-Type: image/png\r\n\r\n";
   string tail = "\r\n--" + boundary + "--\r\n";

   uchar head_b[], tail_b[], body[];
   int head_n = StringToCharArray(head, head_b, 0, WHOLE_ARRAY, CP_UTF8) - 1;  // sin el nulo
   int tail_n = StringToCharArray(tail, tail_b, 0, WHOLE_ARRAY, CP_UTF8) - 1;
   if(head_n < 0 || tail_n < 0)
      return false;

   ArrayResize(body, head_n + image_size + tail_n);
   ArrayCopy(body, head_b,  0,                    0, head_n);
   ArrayCopy(body, image,   head_n,               0, image_size);
   ArrayCopy(body, tail_b,  head_n + image_size,  0, tail_n);

   uchar result[];
   string result_headers;
   ResetLastError();
   int code = WebRequest("POST", "https://api.telegram.org/bot" + token + "/sendPhoto",
                         "Content-Type: multipart/form-data; boundary=" + boundary + "\r\n",
                         10000, body, result, result_headers);

   if(code == -1)
   {
      Print("StructuralLeadSync: WebRequest (foto) fallo. Error=", GetLastError(),
            " (habilita https://api.telegram.org en Herramientas > Opciones > Asesores Expertos)");
      return false;
   }

   if(code != 200)
   {
      Print("StructuralLeadSync: Telegram sendPhoto respondio HTTP ", code, " -> ",
            CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8));
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
bool ReadCredentials(string &token, string &chat_id)
{
   int h = FileOpen(CredentialsFile, FILE_READ | FILE_TXT | FILE_COMMON | FILE_ANSI);
   if(h == INVALID_HANDLE)
      return false;

   while(!FileIsEnding(h))
   {
      string line = FileReadString(h);
      StringTrimLeft(line);
      StringTrimRight(line);
      if(StringLen(line) == 0 || StringGetCharacter(line, 0) == '#')
         continue;

      int sep = StringFind(line, "=");
      if(sep <= 0)
         continue;

      string key = StringSubstr(line, 0, sep);
      string val = StringSubstr(line, sep + 1);
      StringTrimLeft(key);   StringTrimRight(key);
      StringTrimLeft(val);   StringTrimRight(val);

      if(key == "token")        token   = val;
      else if(key == "chat_id") chat_id = val;
   }
   FileClose(h);

   return (StringLen(token) > 0 && StringLen(chat_id) > 0);
}

//+------------------------------------------------------------------+
bool SendTelegram(const string token, const string chat_id, const string text)
{
   string url  = "https://api.telegram.org/bot" + token + "/sendMessage";
   string body = "chat_id=" + chat_id + "&text=" + UrlEncode(text);

   char post[], result[];
   string result_headers;
   StringToCharArray(body, post, 0, StringLen(body), CP_UTF8);
   ArrayResize(post, StringLen(body));   // sin el terminador nulo

   ResetLastError();
   int code = WebRequest("POST", url,
                         "Content-Type: application/x-www-form-urlencoded\r\n",
                         5000, post, result, result_headers);

   if(code == -1)
   {
      // 4060 = WebRequest no permitido para esa URL en Opciones.
      Print("StructuralLeadSync: WebRequest fallo. Error=", GetLastError(),
            " (habilita https://api.telegram.org en Herramientas > Opciones > Asesores Expertos)");
      return false;
   }

   if(code != 200)
   {
      Print("StructuralLeadSync: Telegram respondio HTTP ", code, " -> ",
            CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8));
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
string UrlEncode(const string text)
{
   string out = "";
   uchar bytes[];
   int n = StringToCharArray(text, bytes, 0, StringLen(text), CP_UTF8);

   for(int i = 0; i < n; i++)
   {
      uchar c = bytes[i];
      bool unreserved = (c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') ||
                        (c >= 'a' && c <= 'z') || c == '-' || c == '_' || c == '.' || c == '~';
      if(unreserved)
         out += CharToString(c);
      else
         out += StringFormat("%%%02X", c);
   }
   return out;
}

//+------------------------------------------------------------------+
//| OBJ_LABEL se posiciona por pixeles desde una esquina, asi que      |
//| centrar exige medir el texto. TextSetFont toma el tamano en        |
//| decimas de punto cuando es negativo.                               |
//+------------------------------------------------------------------+
//+------------------------------------------------------------------+
//| Cuantos puntos hay que bajarle a la fuente para que las tres       |
//| lineas quepan en el ancho util del grafico. 0 = cabe tal cual.     |
//+------------------------------------------------------------------+
int FitDrop(const string main, const string detail, const string data)
{
   if(!AutoFitText)
      return 0;

   long chart_width = ChartGetInteger(0, CHART_WIDTH_IN_PIXELS);
   if(chart_width <= 0)
      return 0;

   int usable = (int)chart_width - 24;   // margen a ambos lados
   int max_drop = MathMax(0, FontSize - MathMax(1, MinFontSize));

   for(int drop = 0; drop <= max_drop; drop++)
   {
      if(TextWidth(main,   FontSize + 3 - drop) <= usable &&
         TextWidth(detail, FontSize - drop)     <= usable &&
         TextWidth(data,   FontSize - drop)     <= usable)
         return drop;
   }
   return max_drop;
}

//+------------------------------------------------------------------+
int TextWidth(const string text, const int size)
{
   uint w = 0, h = 0;
   TextSetFont("Arial Bold", -MathMax(1, size) * 10, 0, 0);
   if(!TextGetSize(text, w, h))
      return 0;
   return (int)w;
}

//+------------------------------------------------------------------+
int CenteredX(const string text, const int size)
{
   long chart_width = ChartGetInteger(0, CHART_WIDTH_IN_PIXELS);
   if(chart_width <= 0)
      return 12;

   uint w = 0, h = 0;
   TextSetFont("Arial Bold", -size * 10, 0, 0);
   if(!TextGetSize(text, w, h) || w == 0)
      return 12;

   int x = (int)((chart_width - (long)w) / 2);
   return MathMax(0, x);
}

//+------------------------------------------------------------------+
void Label(const string name, const int y, const string text, const color paint, const int size)
{
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);

   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, CenterText ? CenteredX(text, size) : 12);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetString(0, name, OBJPROP_FONT, "Arial Bold");
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, size);
   ObjectSetInteger(0, name, OBJPROP_COLOR, paint);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
}
//+------------------------------------------------------------------+
