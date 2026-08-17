//+------------------------------------------------------------------+
//| CandleCursorCounter.mq5                                          |
//| Cuenta velas entre dos cursores manuales A y B.                  |
//|                                                                  |
//| Shift + click = Cursor A                                         |
//| Ctrl  + click = Cursor B                                         |
//|                                                                  |
//| Port del indicador ATAS 18_Candle_Cursor_Counter.                |
//| Solo lectura: no coloca ordenes ni escribe archivos.             |
//+------------------------------------------------------------------+
#property copyright "Eddieware"
#property version   "1.00"
#property indicator_chart_window
#property indicator_plots 0

input bool   EnableMousePlacement = true;   // Colocar cursores con el mouse (Shift=A, Ctrl=B)
input bool   IncludeCursorBars    = true;   // Contar tambien las velas de los cursores
input color  CursorAColor         = clrOrange;
input color  CursorBColor         = clrOrange;
input int    CursorLineWidth      = 2;
input bool   ShowNumbers          = true;   // Mostrar numeros sobre las velas
input int    LabelEveryNBars      = 1;      // Etiquetar cada N velas
input int    LabelOffsetPixels    = 20;     // Separacion sobre la vela (pixeles)
input color  NumberColor          = clrWhite;
input int    NumberFontSize       = 10;
input bool   ShowSummary          = true;   // Mostrar resumen
input bool   ShowHint             = true;   // Mostrar aviso cuando no hay cursores
input color  SummaryColor         = clrWhite;
input int    SummaryX             = 10;     // Posicion X del resumen (pixeles)
input int    SummaryY             = 20;     // Posicion Y del resumen (pixeles)
input int    SummaryFontSize      = 10;
input bool   AutoFitSummary       = true;   // Encoger la fuente si no cabe (mosaico)
input int    MinSummaryFontSize   = 6;

#define PREFIX      "CCC_"
#define OBJ_CURSORA PREFIX "cursorA"
#define OBJ_CURSORB PREFIX "cursorB"
#define OBJ_LBLA    PREFIX "labelA"
#define OBJ_LBLB    PREFIX "labelB"
#define OBJ_SUMMARY PREFIX "summary"
#define OBJ_NUM     PREFIX "num_"

datetime cursor_a_time = 0;
datetime cursor_b_time = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   ChartSetInteger(0, CHART_EVENT_MOUSE_MOVE, true);
   IndicatorSetString(INDICATOR_SHORTNAME, "Candle Cursor Counter");
   Redraw();
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   ObjectsDeleteAll(0, PREFIX);
   ChartRedraw();
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
   // Nuevas velas mueven las etiquetas: recalcular solo cuando cambia el conteo.
   static int last_total = 0;
   if(rates_total != last_total)
   {
      last_total = rates_total;
      Redraw();
   }
   return rates_total;
}

//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
   if(id == CHARTEVENT_CLICK)
   {
      if(!EnableMousePlacement)
         return;

      // Sin modificador el click pertenece al grafico: no se intercepta.
      bool shift = (TerminalInfoInteger(TERMINAL_KEYSTATE_SHIFT)   & 0x8000) != 0;
      bool ctrl  = (TerminalInfoInteger(TERMINAL_KEYSTATE_CONTROL) & 0x8000) != 0;
      if(shift == ctrl)
         return;

      int      sub_window = 0;
      datetime click_time = 0;
      double   click_price = 0.0;
      if(!ChartXYToTimePrice(0, (int)lparam, (int)dparam, sub_window, click_time, click_price))
         return;

      int shift_index = iBarShift(_Symbol, PERIOD_CURRENT, click_time, false);
      if(shift_index < 0)
         return;

      datetime bar_time = iTime(_Symbol, PERIOD_CURRENT, shift_index);
      if(shift)
         cursor_a_time = bar_time;
      else
         cursor_b_time = bar_time;

      Redraw();
      return;
   }

   // Zoom y scroll cambian la relacion pixel/precio: hay que recolocar los textos.
   if(id == CHARTEVENT_CHART_CHANGE)
      Redraw();
}

//+------------------------------------------------------------------+
void Redraw()
{
   DeleteNumbers();
   ObjectDelete(0, OBJ_SUMMARY);

   DrawCursor(OBJ_CURSORA, OBJ_LBLA, cursor_a_time, CursorAColor, "Cursor A");
   DrawCursor(OBJ_CURSORB, OBJ_LBLB, cursor_b_time, CursorBColor, "Cursor B");

   if(cursor_a_time == 0 && cursor_b_time == 0)
   {
      if(ShowHint)
         DrawSummaryText("Candle Cursor Counter listo  |  Shift+click = Cursor A  |  Ctrl+click = Cursor B");
      ChartRedraw();
      return;
   }

   if(cursor_a_time == 0 || cursor_b_time == 0)
   {
      if(ShowHint)
         DrawSummaryText("Falta un cursor  |  Shift+click = Cursor A  |  Ctrl+click = Cursor B");
      ChartRedraw();
      return;
   }

   int shift_a = iBarShift(_Symbol, PERIOD_CURRENT, cursor_a_time, false);
   int shift_b = iBarShift(_Symbol, PERIOD_CURRENT, cursor_b_time, false);
   if(shift_a < 0 || shift_b < 0)
   {
      ChartRedraw();
      return;
   }

   // Shift mayor = vela mas antigua = mas a la izquierda.
   int oldest = MathMax(shift_a, shift_b);
   int newest = MathMin(shift_a, shift_b);
   if(!IncludeCursorBars)
   {
      oldest--;
      newest++;
   }

   if(oldest < newest || newest < 0)
   {
      ChartRedraw();
      return;
   }

   if(ShowNumbers)
      DrawNumbers(oldest, newest);

   if(ShowSummary)
      DrawSummaryText(BuildSummary(oldest, newest));

   ChartRedraw();
}

//+------------------------------------------------------------------+
void DrawCursor(const string line_name, const string label_name,
                const datetime bar_time, const color line_color, const string caption)
{
   if(bar_time == 0)
   {
      ObjectDelete(0, line_name);
      ObjectDelete(0, label_name);
      return;
   }

   if(ObjectFind(0, line_name) < 0)
      ObjectCreate(0, line_name, OBJ_VLINE, 0, bar_time, 0);

   ObjectSetInteger(0, line_name, OBJPROP_TIME, 0, bar_time);
   ObjectSetInteger(0, line_name, OBJPROP_COLOR, line_color);
   ObjectSetInteger(0, line_name, OBJPROP_WIDTH, CursorLineWidth);
   ObjectSetInteger(0, line_name, OBJPROP_BACK, false);
   ObjectSetInteger(0, line_name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, line_name, OBJPROP_HIDDEN, true);
   ObjectSetString(0, line_name, OBJPROP_TEXT, caption);
}

//+------------------------------------------------------------------+
void DrawNumbers(const int oldest, const int newest)
{
   int step = MathMax(1, LabelEveryNBars);

   for(int s = oldest; s >= newest; s--)
   {
      int number = oldest - s + 1;

      // La primera y la ultima siempre se dibujan para no perder los extremos.
      if(step > 1 && number != 1 && s != newest && ((number - 1) % step) != 0)
         continue;

      datetime bar_time = iTime(_Symbol, PERIOD_CURRENT, s);
      double   bar_high = iHigh(_Symbol, PERIOD_CURRENT, s);
      if(bar_time == 0)
         continue;

      double label_price = PriceAbovePixels(bar_time, bar_high, LabelOffsetPixels);
      string name = OBJ_NUM + IntegerToString(number);

      if(ObjectFind(0, name) < 0)
         ObjectCreate(0, name, OBJ_TEXT, 0, bar_time, label_price);

      ObjectSetInteger(0, name, OBJPROP_TIME, 0, bar_time);
      ObjectSetDouble(0, name, OBJPROP_PRICE, 0, label_price);
      ObjectSetString(0, name, OBJPROP_TEXT, IntegerToString(number));
      ObjectSetString(0, name, OBJPROP_FONT, "Arial Bold");
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, NumberFontSize);
      ObjectSetInteger(0, name, OBJPROP_COLOR, NumberColor);
      ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_LOWER);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   }
}

//+------------------------------------------------------------------+
//| MQL5 ancla los textos por precio, no por pixel. Se convierte el   |
//| maximo a coordenada de pantalla, se restan los pixeles y se       |
//| regresa a precio, para que la separacion no dependa del zoom.     |
//+------------------------------------------------------------------+
double PriceAbovePixels(const datetime bar_time, const double price, const int pixels)
{
   int x = 0, y = 0;
   if(!ChartTimePriceToXY(0, 0, bar_time, price, x, y))
      return price;

   int      sub_window = 0;
   datetime out_time = 0;
   double   out_price = 0.0;
   if(!ChartXYToTimePrice(0, x, y - pixels, sub_window, out_time, out_price))
      return price;

   return out_price;
}

//+------------------------------------------------------------------+
string BuildSummary(const int oldest, const int newest)
{
   int count = oldest - newest + 1;

   double tick_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick_size <= 0.0)
      tick_size = _Point;

   datetime t_from = iTime(_Symbol, PERIOD_CURRENT, oldest);
   datetime t_to   = iTime(_Symbol, PERIOD_CURRENT, newest);
   double   c_from = iClose(_Symbol, PERIOD_CURRENT, oldest);
   double   c_to   = iClose(_Symbol, PERIOD_CURRENT, newest);

   double highest = iHigh(_Symbol, PERIOD_CURRENT, oldest);
   double lowest  = iLow(_Symbol, PERIOD_CURRENT, oldest);
   for(int s = oldest; s >= newest; s--)
   {
      double h = iHigh(_Symbol, PERIOD_CURRENT, s);
      double l = iLow(_Symbol, PERIOD_CURRENT, s);
      if(h > highest) highest = h;
      if(l < lowest)  lowest  = l;
   }

   double move_ticks  = (c_to - c_from) / tick_size;
   double range_ticks = (highest - lowest) / tick_size;

   // El ultimo bar sigue abierto: se mide hasta su apertura, igual que el primero.
   long seconds = (long)(t_to - t_from);

   return StringFormat("%d velas  |  %s  |  cierre %+.0f ticks  |  rango %.0f ticks",
                       count, FormatElapsed(seconds), move_ticks, range_ticks);
}

//+------------------------------------------------------------------+
string FormatElapsed(long seconds)
{
   if(seconds < 0)
      seconds = -seconds;

   if(seconds >= 3600)
      return StringFormat("%dh %02dm", (int)(seconds / 3600), (int)((seconds % 3600) / 60));

   if(seconds >= 60)
      return StringFormat("%dm %02ds", (int)(seconds / 60), (int)(seconds % 60));

   return StringFormat("%ds", (int)seconds);
}

//+------------------------------------------------------------------+
//+------------------------------------------------------------------+
//| En mosaico el grafico es angosto y el resumen se sale o se encima  |
//| con otros indicadores. Se reduce la fuente hasta que quepa en el   |
//| ancho util, en vez de fijar un tamano que solo sirve maximizado.   |
//+------------------------------------------------------------------+
int FittedSummarySize(const string text)
{
   if(!AutoFitSummary)
      return SummaryFontSize;

   long chart_width = ChartGetInteger(0, CHART_WIDTH_IN_PIXELS);
   if(chart_width <= 0)
      return SummaryFontSize;

   int usable = (int)chart_width - SummaryX - 12;
   int floor_size = MathMax(1, MinSummaryFontSize);

   for(int s = SummaryFontSize; s > floor_size; s--)
   {
      uint w = 0, h = 0;
      TextSetFont("Arial", -s * 10, 0, 0);
      if(!TextGetSize(text, w, h))
         return s;
      if((int)w <= usable)
         return s;
   }
   return floor_size;
}

//+------------------------------------------------------------------+
void DrawSummaryText(const string text)
{
   if(ObjectFind(0, OBJ_SUMMARY) < 0)
      ObjectCreate(0, OBJ_SUMMARY, OBJ_LABEL, 0, 0, 0);

   ObjectSetInteger(0, OBJ_SUMMARY, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, OBJ_SUMMARY, OBJPROP_XDISTANCE, SummaryX);
   ObjectSetInteger(0, OBJ_SUMMARY, OBJPROP_YDISTANCE, SummaryY);
   ObjectSetString(0, OBJ_SUMMARY, OBJPROP_TEXT, text);
   ObjectSetString(0, OBJ_SUMMARY, OBJPROP_FONT, "Arial");
   ObjectSetInteger(0, OBJ_SUMMARY, OBJPROP_FONTSIZE, FittedSummarySize(text));
   ObjectSetInteger(0, OBJ_SUMMARY, OBJPROP_COLOR, SummaryColor);
   ObjectSetInteger(0, OBJ_SUMMARY, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, OBJ_SUMMARY, OBJPROP_HIDDEN, true);
}

//+------------------------------------------------------------------+
void DeleteNumbers()
{
   for(int i = ObjectsTotal(0, 0, -1) - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i, 0, -1);
      if(StringFind(name, OBJ_NUM, 0) == 0)
         ObjectDelete(0, name);
   }
}
//+------------------------------------------------------------------+
