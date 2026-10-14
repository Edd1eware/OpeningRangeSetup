using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Linq;
using OFT.Rendering.Context;       // RenderContext
using OFT.Rendering.Tools;         // RenderPen, RenderFont

namespace ATAS.Indicators
{
    // Historical journal navigator. Accepts either the audited Lucid executions
    // or the separately labeled simulated inside-control feed.
    //
    // Reads a flat CSV produced by mbp_mbo_research/scripts/build_inside_control_navigator.py
    // and, whenever the chart shows one of those sessions, draws the full trade on top
    // of the candles: opening range, signal candle, imbalance rows, entry, stop, target
    // and the realised outcome. A side panel lists all 35 trades so the next session to
    // visit is always visible.
    //
    // ATAS exposes no API to move the Replay window, so the jump between sessions stays
    // manual (or is driven from navigate_inside_control_trades.py, which writes the
    // current index into a companion file that this indicator highlights).
    //
    // Pure overlay: submits no orders. Writes its local view state and review
    // evidence only; does not alter the execution strategy.
    [DisplayName("19_Inside_Control_Trade_Navigator")]
    public class InsideControlTradeNavigator : Indicator
    {
        private const decimal FallbackTickSize = 0.25m;
        // Defaults to the real Lucid account positions. Point this at
        // inside_control_trades.csv to review the simulated control instead.
        private const string DefaultCsv =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\lucid_real_trades.csv";
        private const string DefaultCursor =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\inside_control_current.txt";

        // El encuadre no se puede fijar por API: hay que arrastrar la barra de precio.
        // Para poder hacerlo en lazo cerrado desde Python, el indicador publica lo que el
        // grafico esta mostrando ahora mismo.
        private const string DefaultViewState =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\inside_control_view.txt";

        private sealed class ImbalanceRow
        {
            public decimal Low;
            public decimal High;
            public int Volume;
            public int Reference;
            public decimal Ratio;
        }

        private sealed class Trade
        {
            public int N;
            public DateTime Session;          // NY calendar date of the session
            public TimeSpan CandleStart;      // NY open time of the signal candle
            public TimeSpan SignalClose;      // NY close time of the signal candle
            public string Minute = "";
            public int Direction;             // +1 long, -1 short
            public decimal OrHigh, OrLow;
            public decimal Open, High, Low, Close;             // ceil-5 grouped grid
            public decimal RawOpen, RawHigh, RawLow, RawClose; // native Databento grid
            public decimal Vwap;
            public decimal Entry, Stop, Target, Exit;
            public decimal RiskTicks;
            public string Result = "";
            public decimal NetTicks, NetR, NetUsd, Mae, Mfe, DurationSeconds;
            public string EntryClock = "", ExitClock = "";
            public TimeSpan ExitTime = TimeSpan.MinValue;   // NY, truncated to the minute
            public string Source = "", Warn = "";
            public string BracketSource = "", SignalSource = "", GroupKey = "";
            public string ContextEvidencePath = "";
            public int Qty, FillCount;
            public bool ChartContextResolved;
            public List<ImbalanceRow> Imbalances = new();
            public List<RealFill> Fills = new();
        }

        private sealed class RealFill
        {
            public string Id = "", EntryClock = "", ExitClock = "";
            public decimal Qty, Entry, Exit;
        }

        private readonly List<Trade> _trades = new();
        private string _loadError = "";
        private DateTime _csvStamp = DateTime.MinValue;
        private DateTime _lastCheck = DateTime.MinValue;
        private string _csvSha256 = "";
        private int _cursorIndex = -1;

        private readonly RenderFont _font = new("Arial", 11);
        private readonly RenderFont _boldFont = new("Arial", 11, FontStyle.Bold);
        private readonly RenderFont _listFont = new("Consolas", 11);
        private readonly RenderFont _listBoldFont = new("Consolas", 11, FontStyle.Bold);

        public InsideControlTradeNavigator()
        {
            Name = "19_Inside_Control_Trade_Navigator";
            EnableCustomDrawing = true;
            SubscribeToDrawingEvents(DrawingLayouts.Final);
            DrawAbovePrice = true;
            DenyToChangePanel = true;
            Panel = IndicatorDataProvider.CandlesPanel;
        }

        #region Settings

        [Display(Name = "Captura limpia del diario (sin panel ni ficha grande)", GroupName = "Dibujo", Order = 9)]
        public bool JournalCaptureMode { get; set; } = true;

        [Display(Name = "Reconstruir SL/TP desde ultima vela cerrada en ATAS", GroupName = "Dibujo", Order = 18)]
        public bool ReconstructHistoricalBracket { get; set; } = true;

        [Display(Name = "Archivo CSV de trades", GroupName = "Datos", Order = 1)]
        public string CsvPath { get; set; } = DefaultCsv;

        [Display(Name = "Archivo del indice actual (lo escribe el driver)", GroupName = "Datos", Order = 2)]
        public string CursorPath { get; set; } = DefaultCursor;

        [Display(Name = "Archivo de estado de la vista (lo lee el driver)", GroupName = "Datos", Order = 5)]
        public string ViewStatePath { get; set; } = DefaultViewState;

        // ATAS shows candles in the platform timezone, which is not necessarily New York.
        // The CSV is always New York (all 150 sessions are EDT). This offset converts.
        [Display(Name = "Horas del grafico respecto a Nueva York (+3 si el servidor va 3h adelante)",
                 GroupName = "Datos", Order = 3)]
        [Range(-23, 23)]
        public int ChartToNyOffsetHours { get; set; } = 0;

        [Display(Name = "Recargar el CSV ahora (se auto-desactiva)", GroupName = "Datos", Order = 4)]
        public bool ReloadNow
        {
            get => false;
            set
            {
                if (!value)
                    return;

                _csvStamp = DateTime.MinValue;
                LoadIfChanged(force: true);
                RedrawChart();
            }
        }

        [Display(Name = "Dibujar el rango de apertura", GroupName = "Dibujo", Order = 10)]
        public bool ShowOpeningRange { get; set; } = true;

        [Display(Name = "Dibujar entrada, SL y TP", GroupName = "Dibujo", Order = 11)]
        public bool ShowOrders { get; set; } = true;

        // The user's own ATAS screenshots mark a trade with two filled boxes spanning
        // from the entry bar to the exit: risk between entry and stop, reward between
        // entry and target. Mirroring that makes a marked trade obvious at a glance.
        [Display(Name = "Dibujar cajas de riesgo y objetivo", GroupName = "Dibujo", Order = 15)]
        public bool ShowRiskRewardBoxes { get; set; } = true;

        [Display(Name = "Opacidad de las cajas", GroupName = "Dibujo", Order = 16)]
        [Range(10, 200)]
        public int BoxOpacity { get; set; } = 70;

        // When the exit bar cannot be resolved the boxes still need a right edge.
        [Display(Name = "Barras de ancho si no encuentro la vela de salida", GroupName = "Dibujo", Order = 17)]
        [Range(1, 120)]
        public int FallbackBoxBars { get; set; } = 10;

        [Display(Name = "Dibujar las filas de imbalance", GroupName = "Dibujo", Order = 12)]
        public bool ShowImbalances { get; set; } = true;

        [Display(Name = "Marcar la vela de senal", GroupName = "Dibujo", Order = 13)]
        public bool ShowSignalCandle { get; set; } = true;

        [Display(Name = "Mostrar la ficha de la operacion", GroupName = "Dibujo", Order = 14)]
        public bool ShowTradeCard { get; set; } = true;

        [Display(Name = "Mostrar el panel de operaciones", GroupName = "Panel", Order = 20)]
        public bool ShowList { get; set; } = true;

        [Display(Name = "Filas visibles alrededor de la actual", GroupName = "Panel", Order = 21)]
        [Range(3, 35)]
        public int ListWindow { get; set; } = 13;

        [Display(Name = "Panel a la derecha (si no, a la izquierda)", GroupName = "Panel", Order = 22)]
        public bool ListOnRight { get; set; } = true;

        [Display(Name = "Color de compra", GroupName = "Colores", Order = 30)]
        public Color LongColor { get; set; } = Color.FromArgb(63, 185, 80);

        [Display(Name = "Color de venta", GroupName = "Colores", Order = 31)]
        public Color ShortColor { get; set; } = Color.FromArgb(248, 81, 73);

        [Display(Name = "Color del rango de apertura", GroupName = "Colores", Order = 32)]
        public Color OrColor { get; set; } = Color.FromArgb(167, 139, 250);

        [Display(Name = "Color de la entrada", GroupName = "Colores", Order = 33)]
        public Color EntryColor { get; set; } = Color.FromArgb(110, 168, 254);

        [Display(Name = "Color de la caja de riesgo", GroupName = "Colores", Order = 35)]
        public Color RiskBoxColor { get; set; } = Color.FromArgb(142, 34, 34);

        [Display(Name = "Color de la caja de objetivo", GroupName = "Colores", Order = 36)]
        public Color RewardBoxColor { get; set; } = Color.FromArgb(21, 104, 94);

        [Display(Name = "Color del texto", GroupName = "Colores", Order = 34)]
        public Color TextColor { get; set; } = Color.White;

        #endregion

        private readonly TimeSpan _reviewTimerPeriod = TimeSpan.FromMilliseconds(500);
        private bool _reviewTimerSubscribed;

        protected override void OnInitialize()
        {
            base.OnInitialize();
            SubscribeToTimer(_reviewTimerPeriod, RequestReviewRedraw);
            _reviewTimerSubscribed = true;
        }

        private void RequestReviewRedraw() => RedrawChart();

        protected override void OnDispose()
        {
            if (_reviewTimerSubscribed)
            {
                try { UnsubscribeFromTimer(_reviewTimerPeriod, RequestReviewRedraw); }
                catch { }
                _reviewTimerSubscribed = false;
            }
            base.OnDispose();
        }

        protected override void OnCalculate(int bar, decimal value) { }

        #region CSV loading

        private void LoadIfChanged(bool force = false)
        {
            // OnRender fires on every frame; stat the file at most twice a second.
            var now = DateTime.UtcNow;
            if (!force && (now - _lastCheck).TotalMilliseconds < 500)
                return;

            _lastCheck = now;

            try
            {
                var info = new FileInfo(CsvPath);
                if (!info.Exists)
                {
                    _trades.Clear();
                    _loadError = "No existe el CSV: " + CsvPath;
                    return;
                }

                if (!force && info.LastWriteTimeUtc == _csvStamp)
                {
                    ReadCursor();
                    return;
                }

                _csvStamp = info.LastWriteTimeUtc;
                ParseCsv();
                ReadCursor();
            }
            catch (Exception ex)
            {
                _trades.Clear();
                _loadError = "Error leyendo el CSV: " + ex.Message;
            }
        }

        private void ParseCsv()
        {
            _trades.Clear();
            _loadError = "";

            // Copy first: the builder may be rewriting the file while ATAS reads it.
            string[] lines;
            using (var stream = new FileStream(CsvPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            using (var copy = new MemoryStream())
            {
                stream.CopyTo(copy);
                var bytes = copy.ToArray();
                _csvSha256 = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes)).ToLowerInvariant();
                lines = System.Text.Encoding.UTF8.GetString(bytes).TrimStart('\uFEFF').Split('\n');
            }

            if (lines.Length < 2)
            {
                _loadError = "El CSV no tiene filas de datos.";
                return;
            }

            var header = lines[0].Trim().Split(';');
            var index = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            for (var i = 0; i < header.Length; i++)
                index[header[i].Trim()] = i;

            for (var i = 1; i < lines.Length; i++)
            {
                var line = lines[i].Trim();
                if (line.Length == 0)
                    continue;

                var cells = line.Split(';');

                string Cell(string name) =>
                    index.TryGetValue(name, out var pos) && pos < cells.Length ? cells[pos].Trim() : "";

                decimal Dec(string name) =>
                    decimal.TryParse(Cell(name), NumberStyles.Any, CultureInfo.InvariantCulture, out var v) ? v : 0m;

                int Int(string name) =>
                    int.TryParse(Cell(name), NumberStyles.Any, CultureInfo.InvariantCulture, out var v) ? v : 0;

                try
                {
                    var trade = new Trade
                    {
                        N = Int("n"),
                        Session = DateTime.ParseExact(Cell("session"), "yyyy-MM-dd",
                                                      CultureInfo.InvariantCulture),
                        CandleStart = TimeSpan.Parse(Cell("candle_start"), CultureInfo.InvariantCulture),
                        SignalClose = TimeSpan.Parse(Cell("signal_close"), CultureInfo.InvariantCulture),
                        Minute = Cell("minute"),
                        Direction = Int("dir"),
                        OrHigh = Dec("or_high"),
                        OrLow = Dec("or_low"),
                        Open = Dec("o"), High = Dec("h"), Low = Dec("l"), Close = Dec("c"),
                        RawOpen = Dec("raw_o"), RawHigh = Dec("raw_h"),
                        RawLow = Dec("raw_l"), RawClose = Dec("raw_c"),
                        Vwap = Dec("vwap"),
                        Entry = Dec("entry"), Stop = Dec("stop"),
                        Target = Dec("target"), Exit = Dec("exit"),
                        RiskTicks = Dec("risk_ticks"),
                        Result = Cell("result"),
                        NetTicks = Dec("net_ticks"), NetR = Dec("net_r"), NetUsd = Dec("net_usd"),
                        Mae = Dec("mae"), Mfe = Dec("mfe"),
                        DurationSeconds = Dec("duration_s"),
                        EntryClock = Cell("entry_clock"), ExitClock = Cell("exit_clock"),
                        Source = Cell("source"), Warn = Cell("warn"),
                        BracketSource = Cell("bracket_source"), SignalSource = Cell("signal_candle_source"),
                        GroupKey = Cell("group_key"), Qty = Int("qty"), FillCount = Int("fill_count"),
                    };

                    foreach (var packedFill in Cell("fills").Split('|'))
                    {
                        var f = packedFill.Split(',');
                        if (f.Length != 8) continue;
                        trade.Fills.Add(new RealFill
                        {
                            Id = f[0], Qty = decimal.Parse(f[1], CultureInfo.InvariantCulture),
                            EntryClock = f[2], Entry = decimal.Parse(f[3], CultureInfo.InvariantCulture),
                            ExitClock = f[4], Exit = decimal.Parse(f[5], CultureInfo.InvariantCulture),
                        });
                    }

                    // "09:36:01.793" -> 09:36:00, the open time of the bar holding the exit.
                    if (TimeSpan.TryParse(trade.ExitClock, CultureInfo.InvariantCulture, out var exitAt))
                        trade.ExitTime = new TimeSpan(exitAt.Hours, exitAt.Minutes, 0);

                    foreach (var packed in Cell("imb_rows").Split('|'))
                    {
                        // lo:hi:vol:ref:ratio
                        var parts = packed.Split(':');
                        if (parts.Length < 5)
                            continue;

                        trade.Imbalances.Add(new ImbalanceRow
                        {
                            Low = decimal.Parse(parts[0], CultureInfo.InvariantCulture),
                            High = decimal.Parse(parts[1], CultureInfo.InvariantCulture),
                            Volume = int.Parse(parts[2], CultureInfo.InvariantCulture),
                            Reference = int.Parse(parts[3], CultureInfo.InvariantCulture),
                            Ratio = decimal.Parse(parts[4], CultureInfo.InvariantCulture),
                        });
                    }

                    _trades.Add(trade);
                }
                catch (Exception ex)
                {
                    _loadError = $"Fila {i} ilegible: {ex.Message}";
                }
            }

            _trades.Sort((a, b) => a.N.CompareTo(b.N));
        }

        private void ReadCursor()
        {
            try
            {
                if (!File.Exists(CursorPath))
                    return;

                using var stream = new FileStream(CursorPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
                using var reader = new StreamReader(stream);
                var text = reader.ReadToEnd().Trim();
                if (int.TryParse(text, NumberStyles.Any, CultureInfo.InvariantCulture, out var n))
                    _cursorIndex = n;
            }
            catch
            {
                // The driver may be mid-write; the stale value is good enough for one frame.
            }
        }

        #endregion

        #region Rendering

        protected override void OnRender(RenderContext context, DrawingLayouts layout)
        {
            if (ChartInfo == null || Container == null || CurrentBar <= 1)
                return;

            LoadIfChanged();

            var region = Container.Region;

            if (_trades.Count == 0)
            {
                DrawBoxedText(context, string.IsNullOrEmpty(_loadError)
                    ? "19_Inside_Control: CSV vacio."
                    : "19_Inside_Control: " + _loadError, Color.Orange, region.Left + 8, region.Top + 8);
                return;
            }

            var trade = FindTradeForChart(out var sessionDate);

            if (trade != null)
                DrawTrade(context, trade, region);
            else
                DrawBoxedText(context,
                    $"Diario: la sesion {sessionDate:yyyy-MM-dd} no esta en el CSV ({_trades.Count} entradas).",
                    Color.Orange, region.Left + 8, region.Top + 8);

            if (ShowList && !JournalCaptureMode)
                DrawList(context, trade, region);

            PublishViewState(trade, region);
        }

        private DateTime _lastPublish = DateTime.MinValue;

        /// <summary>
        /// Publica lo que el grafico muestra ahora: rango de precio visible, primera y
        /// ultima vela visibles y el OR de la sesion. El driver lo lee para arrastrar la
        /// barra de precio hasta el encuadre correcto, que depende del tamano del OR y
        /// por tanto cambia en cada sesion.
        /// </summary>
        private void PublishViewState(Trade? trade, Rectangle region)
        {
            var now = DateTime.UtcNow;
            if ((now - _lastPublish).TotalMilliseconds < 400)
                return;

            _lastPublish = now;

            try
            {
                // No hay API para leer el eje de precio, pero si para proyectar un precio
                // a pixel. Con dos precios conocidos se invierte la recta.
                decimal refHigh = trade?.OrHigh ?? 0m, refLow = trade?.OrLow ?? 0m;
                if (refHigh <= 0 || refLow <= 0 || refHigh == refLow)
                {
                    var candle = GetCandle(CurrentBar - 1);
                    refHigh = candle.High;
                    refLow = candle.Low;
                }

                if (refHigh <= 0 || refLow <= 0 || refHigh == refLow)
                    return;

                var yHigh = Chart.GetYByPrice(refHigh, true);
                var yLow = Chart.GetYByPrice(refLow, true);
                if (yHigh == yLow)
                    return;

                var pricePerPixel = (refLow - refHigh) / (decimal)(yLow - yHigh);
                var topPrice = refHigh + ((decimal)(region.Top - yHigh) * pricePerPixel);
                var bottomPrice = refHigh + ((decimal)(region.Bottom - yHigh) * pricePerPixel);

                var container = Chart.PriceChartContainer;
                var first = Math.Max(0, container.FirstVisibleBarNumber);
                var last = Math.Min(CurrentBar - 1, container.LastVisibleBarNumber);

                var lines = new[]
                {
                    $"top={topPrice.ToString("0.00", CultureInfo.InvariantCulture)}",
                    $"bottom={bottomPrice.ToString("0.00", CultureInfo.InvariantCulture)}",
                    $"range={(topPrice - bottomPrice).ToString("0.00", CultureInfo.InvariantCulture)}",
                    $"bars={last - first + 1}",
                    $"first_time={ToNy(GetCandle(first).Time):yyyy-MM-dd HH:mm}",
                    $"last_time={ToNy(GetCandle(last).Time):yyyy-MM-dd HH:mm}",
                    $"or_high={(trade?.OrHigh ?? 0m).ToString("0.00", CultureInfo.InvariantCulture)}",
                    $"or_low={(trade?.OrLow ?? 0m).ToString("0.00", CultureInfo.InvariantCulture)}",
                    $"entry={(trade?.Entry ?? 0m).ToString("0.00", CultureInfo.InvariantCulture)}",
                    $"stop={(trade?.Stop ?? 0m).ToString("0.00", CultureInfo.InvariantCulture)}",
                    $"target={(trade?.Target ?? 0m).ToString("0.00", CultureInfo.InvariantCulture)}",
                    $"session={(trade != null ? trade.Session.ToString("yyyy-MM-dd") : "")}",
                    $"timestamp_utc={DateTime.UtcNow:O}",
                    $"trade_n={trade?.N ?? 0}",
                    $"cursor_n={_cursorIndex}",
                    $"group_key={trade?.GroupKey ?? ""}",
                    $"entry_clock={trade?.EntryClock ?? ""}",
                    $"exit_clock={trade?.ExitClock ?? ""}",
                    $"exit={(trade?.Exit ?? 0m).ToString("0.########", CultureInfo.InvariantCulture)}",
                    $"entry_bar_visible={IsClockVisible(trade, trade?.EntryClock)}",
                    $"exit_bar_visible={IsClockVisible(trade, trade?.ExitClock)}",
                    $"signal_bar_visible={(trade != null && FindBarByNyTime(trade.Session, trade.CandleStart) is var sb && sb >= 0 && IsNearVisible(sb))}",
                    $"bracket_source={trade?.BracketSource ?? ""}",
                    $"signal_candle_source={trade?.SignalSource ?? ""}",
                    $"context_evidence_path={trade?.ContextEvidencePath ?? ""}",
                    $"journal_mode={JournalCaptureMode}",
                    $"csv_path={CsvPath}",
                    $"csv_sha256={_csvSha256}",
                    $"bars_width={Chart.PriceChartContainer.BarsWidth.ToString(CultureInfo.InvariantCulture)}",
                    $"last_available_time={ToNy(GetCandle(CurrentBar - 1).Time):yyyy-MM-dd HH:mm}",
                    $"region_right={region.Right}",
                    $"region_top={region.Top}",
                    $"region_bottom={region.Bottom}",
                };

                var temporary = ViewStatePath + ".tmp";
                File.WriteAllText(temporary, string.Join("\n", lines));
                File.Move(temporary, ViewStatePath, true);
            }
            catch
            {
                // El driver puede estar leyendo el archivo; se reintenta en el siguiente frame.
            }
        }

        // The chart shows one session at a time during replay. Take the New York date of
        // the last bar and look it up; this keeps working when the chart is scrolled.
        private Trade? FindTradeForChart(out DateTime sessionDate)
        {
            var date = ToNy(GetCandle(CurrentBar - 1).Time).Date;
            sessionDate = date;
            return _trades.FirstOrDefault(t => t.Session == date && t.N == _cursorIndex)
                ?? _trades.FirstOrDefault(t => t.Session == date);
        }

        private DateTime ToNy(DateTime chartTime) => chartTime.AddHours(-ChartToNyOffsetHours);

        private void DrawTrade(RenderContext context, Trade trade, Rectangle region)
        {
            var signalBar = FindBarByNyTime(trade.Session, trade.CandleStart);
            ResolveHistoricalContext(trade, signalBar);
            var dirColor = trade.Direction > 0 ? LongColor : ShortColor;

            if (ShowOpeningRange)
            {
                var orColor = JournalCaptureMode ? Color.Red : OrColor;
                DrawPriceLine(context, trade.OrHigh, orColor, region, "OR high 09:30", dash: false);
                DrawPriceLine(context, trade.OrLow, orColor, region, "OR low 09:30", dash: false);
                if (!JournalCaptureMode)
                    ShadeBetween(context, trade.OrHigh, trade.OrLow, Color.FromArgb(28, OrColor), region);
            }

            if (ShowImbalances && signalBar >= 0 && !JournalCaptureMode)
            {
                foreach (var row in trade.Imbalances)
                {
                    ShadeBetween(context, row.High, row.Low, Color.FromArgb(55, dirColor), region);
                    var y = Chart.GetYByPrice(row.High, true);
                    var ratio = row.Ratio >= 999m ? "inf" : row.Ratio.ToString("0.0", CultureInfo.InvariantCulture);
                    context.DrawString(
                        $"imb {row.Volume}x{row.Reference} r{ratio}",
                        _font, dirColor, region.Left + 10, y - 14);
                }
            }

            if (ShowRiskRewardBoxes)
                DrawRiskRewardBoxes(context, trade, signalBar, region);

            if (ShowOrders)
            {
                var reconstructed = trade.BracketSource.StartsWith("reconstructed", StringComparison.OrdinalIgnoreCase);
                DrawPriceLine(context, trade.Stop, ShortColor, region, (reconstructed ? "SL reconstruido " : "SL ") + Fmt(trade.Stop));
                DrawPriceLine(context, trade.Target, LongColor, region, (reconstructed ? "TP 1:1 reconstruido " : "TP ") + Fmt(trade.Target));
                DrawPriceLine(context, trade.Entry, JournalCaptureMode ? Color.White : EntryColor, region,
                    (trade.Direction > 0 ? "COMPRA " : "VENTA ") + Fmt(trade.Entry));
            }

            // Real-account rows carry no engine candle, so there is no OHLC to outline.
            DrawRealExits(context, trade, region);
            if (ShowSignalCandle && trade.High > 0 && signalBar >= 0 && IsNearVisible(signalBar) && !JournalCaptureMode)
                OutlineSignalCandle(context, signalBar, trade, dirColor);

            if (JournalCaptureMode)
                DrawJournalCaption(context, trade, region);
            else if (ShowTradeCard)
                DrawTradeCard(context, trade, signalBar, region);
        }

        // Two filled boxes from the entry bar to the exit bar, in the style the user
        // already marks his own charts with: risk between entry and stop, reward between
        // entry and target. Makes an already-reviewed trade obvious at a glance.
        private void DrawRiskRewardBoxes(RenderContext context, Trade trade, int signalBar, Rectangle region)
        {
            if (trade.Entry <= 0)
                return;

            // A real account records only the entry and the exit. Without a stop and a
            // target there is nothing to split into risk and reward, so the position is
            // painted as a single box coloured by its outcome.
            var hasBracket = trade.Stop > 0 && trade.Target > 0;
            if (!hasBracket && trade.Exit <= 0)
                return;

            // The position starts on the bar after the signal closes.
            var fromBar = FindClockBar(trade, trade.EntryClock);
            if (fromBar < 0) return;

            var exitBar = trade.ExitTime == TimeSpan.MinValue
                ? -1
                : FindBarByNyTime(trade.Session, trade.ExitTime);
            if (exitBar < fromBar)
                exitBar = Math.Min(fromBar + FallbackBoxBars, CurrentBar - 1);

            var barsWidth = Math.Max(2, (int)Chart.PriceChartContainer.BarsWidth);
            var left = Chart.GetXByBar(fromBar, true);
            var right = Chart.GetXByBar(exitBar, true) + barsWidth;
            right = Math.Max(right, left + 2 * barsWidth);

            // Clip to the visible region so a trade scrolled half off-screen still draws.
            left = Math.Max(left, region.Left);
            right = Math.Min(right, region.Right);
            if (right <= left)
                return;

            var opacity = Math.Clamp(BoxOpacity, 10, 200);

            if (hasBracket)
            {
                FillPriceBox(context, trade.Entry, trade.Stop, Color.FromArgb(opacity, RiskBoxColor),
                             left, right, region);
                FillPriceBox(context, trade.Entry, trade.Target, Color.FromArgb(opacity, RewardBoxColor),
                             left, right, region);
            }
            else
            {
                var outcome = trade.NetTicks > 0 ? RewardBoxColor : RiskBoxColor;
                FillPriceBox(context, trade.Entry, trade.Exit, Color.FromArgb(opacity, outcome),
                             left, right, region);
            }

            // Entry marker: a thick segment on the entry price across the two boxes.
            var entryY = Chart.GetYByPrice(trade.Entry, true);
            if (entryY >= region.Top && entryY <= region.Bottom)
                context.DrawLine(new RenderPen(EntryColor, 3), left, entryY, right, entryY);
        }

        private void FillPriceBox(RenderContext context, decimal priceA, decimal priceB,
                                  Color color, int left, int right, Rectangle region)
        {
            var yA = Chart.GetYByPrice(priceA, true);
            var yB = Chart.GetYByPrice(priceB, true);

            var top = Math.Max(Math.Min(yA, yB), region.Top);
            var bottom = Math.Min(Math.Max(yA, yB), region.Bottom);
            if (bottom <= top)
                return;

            context.FillRectangle(color, new Rectangle(left, top, right - left, bottom - top));
        }

        private void OutlineSignalCandle(RenderContext context, int bar, Trade trade, Color color)
        {
            var width = Math.Max(6, (int)Chart.PriceChartContainer.BarsWidth);
            var x = Chart.GetXByBar(bar, true);
            var top = Chart.GetYByPrice(trade.High, true);
            var bottom = Chart.GetYByPrice(trade.Low, true);

            var box = new Rectangle(x - 2, top - 2, width + 4, Math.Max(bottom - top, 4) + 4);
            context.DrawRectangle(new RenderPen(color, 2), box);

            var label = $"senal {trade.Minute}";
            var size = context.MeasureString(label, _boldFont);
            context.DrawString(label, _boldFont, color, box.Left, box.Top - size.Height - 2);
        }

        private void DrawTradeCard(RenderContext context, Trade trade, int signalBar, Rectangle region)
        {
            var win = trade.NetTicks > 0;
            var resultColor = win ? LongColor : ShortColor;

            // Does the chart actually show the candle the engine modelled? This is the
            // cheapest ATAS/Databento parity check available while reviewing.
            string parity;
            Color parityColor;
            if (trade.RawHigh <= 0)
            {
                parity = "Operacion real de la cuenta: no hay vela del motor con la que comparar.";
                parityColor = TextColor;
            }
            else if (signalBar < 0)
            {
                parity = $"No encontre la vela {trade.Minute} NY (ajusta el offset horario, ahora {ChartToNyOffsetHours:+0;-0;0}h).";
                parityColor = Color.Orange;
            }
            else
            {
                var candle = GetCandle(signalBar);
                var tick = GetTickSize();
                var match =
                    Math.Abs(candle.High - trade.RawHigh) <= tick &&
                    Math.Abs(candle.Low - trade.RawLow) <= tick &&
                    Math.Abs(candle.Close - trade.RawClose) <= tick;
                parity = match
                    ? "La vela de ATAS coincide con la del motor (+-1 tick)."
                    : $"DIFIERE: ATAS H/L/C {Fmt(candle.High)}/{Fmt(candle.Low)}/{Fmt(candle.Close)} " +
                      $"vs motor {Fmt(trade.RawHigh)}/{Fmt(trade.RawLow)}/{Fmt(trade.RawClose)}.";
                parityColor = match ? LongColor : Color.Orange;
            }

            var duration = trade.DurationSeconds < 60m
                ? $"{trade.DurationSeconds:0.0} s"
                : $"{trade.DurationSeconds / 60m:0.0} min";

            var lines = new List<(string Text, Color Color)>
            {
                ($"TRADE {trade.N}/{_trades.Count}   {trade.Session:yyyy-MM-dd}   {(trade.Direction > 0 ? "COMPRA" : "VENTA")}   vela {trade.Minute}",
                    trade.Direction > 0 ? LongColor : ShortColor),
                ($"Entrada {Fmt(trade.Entry)} a las {trade.EntryClock}" +
                 (trade.Stop > 0 ? $"   |   SL {Fmt(trade.Stop)}" : "") +
                 (trade.Target > 0 ? $"   |   TP {Fmt(trade.Target)}" : ""), TextColor),
                ((trade.RiskTicks > 0 ? $"Riesgo {trade.RiskTicks:0} ticks   |   " : "") +
                 (trade.OrHigh > 0 ? $"OR {Fmt(trade.OrLow)} - {Fmt(trade.OrHigh)}" : "OR no disponible") +
                 (trade.Vwap > 0 ? $"   |   VWAP {Fmt(trade.Vwap)}" : ""), TextColor),
                ($"{trade.Result}: {(trade.NetTicks > 0 ? "+" : "")}{trade.NetTicks:0.0} ticks   " +
                 (trade.NetR != 0 ? $"{(trade.NetR > 0 ? "+" : "")}{trade.NetR:0.00} R   " : "") +
                 $"{(trade.NetUsd > 0 ? "+" : "")}{trade.NetUsd:0} USD   |   salida {Fmt(trade.Exit)} a las {trade.ExitClock} ({duration})", resultColor),
                ((trade.Mfe > 0 || trade.Mae > 0 ? $"MAE {trade.Mae:0} / MFE {trade.Mfe:0} ticks   |   " : "") +
                 $"origen {trade.Source}", TextColor),
                (parity, parityColor),
            };

            if (!string.IsNullOrEmpty(trade.Warn))
                lines.Add(("Advertencia: " + trade.Warn.Replace(",", ", "), Color.Orange));

            DrawPanel(context, lines, region.Left + 8, region.Top + 8, _font);
        }

        private void DrawList(RenderContext context, Trade? current, Rectangle region)
        {
            // The driver's cursor wins when it points at a real row; otherwise follow the
            // session the chart is showing.
            var activeN = _cursorIndex > 0 ? _cursorIndex : current?.N ?? -1;
            var activeIndex = _trades.FindIndex(t => t.N == activeN);
            if (activeIndex < 0)
                activeIndex = 0;

            var window = Math.Min(ListWindow, _trades.Count);
            var start = Math.Max(0, Math.Min(activeIndex - (window / 2), _trades.Count - window));

            var lines = new List<(string Text, Color Color)>
            {
                ($"OPERACIONES ({_trades.Count})", TextColor),
            };

            if (start > 0)
                lines.Add(($"   ... {start} antes", Color.Gray));

            for (var i = start; i < start + window; i++)
            {
                var t = _trades[i];
                var marker = t.N == activeN ? "<" : " ";
                var chartHere = current != null && current.N == t.N ? "*" : " ";
                var text = string.Format(
                    CultureInfo.InvariantCulture,
                    "{0}{1} {2:00} {3:yyyy-MM-dd} {4} {5} {6,-2} {7,6:+0.0;-0.0}",
                    chartHere, marker, t.N, t.Session, t.Minute,
                    t.Direction > 0 ? "L" : "C", t.Result, t.NetTicks);

                var color = t.N == activeN
                    ? EntryColor
                    : t.NetTicks > 0 ? LongColor : ShortColor;
                lines.Add((text, color));
            }

            var remaining = _trades.Count - (start + window);
            if (remaining > 0)
                lines.Add(($"   ... {remaining} despues", Color.Gray));

            // Computed, never hard-coded: the same indicator serves the simulated control
            // and the real account, and their totals differ.
            var wins = _trades.Count(t => t.NetTicks > 0);
            var grossWin = _trades.Where(t => t.NetUsd > 0).Sum(t => t.NetUsd);
            var grossLoss = Math.Abs(_trades.Where(t => t.NetUsd < 0).Sum(t => t.NetUsd));
            var pf = grossLoss > 0 ? grossWin / grossLoss : 0m;

            lines.Add(($"WR {100m * wins / _trades.Count:0.00}%   PF {pf:0.000}   " +
                       $"neto {_trades.Sum(t => t.NetUsd):+#,##0;-#,##0;0} USD", TextColor));

            var widest = lines.Max(l => context.MeasureString(l.Text, _listFont).Width);
            var x = ListOnRight ? region.Right - widest - 26 : region.Left + 8;
            var y = region.Top + 8 + (ShowTradeCard ? 0 : 0);

            // Keep the list clear of the trade card when both are on the left.
            if (!ListOnRight && ShowTradeCard)
                y = region.Top + 8 + (int)(context.MeasureString("X", _font).Height * 8);

            DrawPanel(context, lines, x, y, _listFont, _listBoldFont);
        }

        #endregion

        #region Drawing primitives

        private void DrawPriceLine(RenderContext context, decimal price, Color color,
                                   Rectangle region, string label, bool dash = false)
        {
            if (price <= 0)
                return;

            var y = Chart.GetYByPrice(price, true);
            if (y < region.Top || y > region.Bottom)
                return;

            var pen = new RenderPen(color, dash ? 1 : 2);
            if (dash)
            {
                // RenderPen has no dash style here, so fake it with short segments.
                for (var x = region.Left; x < region.Right; x += 12)
                    context.DrawLine(pen, x, y, Math.Min(x + 6, region.Right), y);
            }
            else
            {
                context.DrawLine(pen, region.Left, y, region.Right, y);
            }

            var size = context.MeasureString(label, _boldFont);
            var boxX = region.Right - size.Width - 10;
            context.FillRectangle(Color.FromArgb(200, 0, 0, 0),
                new Rectangle(boxX - 4, y - (size.Height / 2) - 1, size.Width + 8, size.Height + 2));
            context.DrawString(label, _boldFont, color, boxX, y - (size.Height / 2));
        }

        private void ShadeBetween(RenderContext context, decimal top, decimal bottom,
                                  Color color, Rectangle region)
        {
            if (top <= 0 || bottom <= 0)
                return;

            var yTop = Chart.GetYByPrice(Math.Max(top, bottom), true);
            var yBottom = Chart.GetYByPrice(Math.Min(top, bottom), true);

            var clippedTop = Math.Max(yTop, region.Top);
            var clippedBottom = Math.Min(yBottom, region.Bottom);
            if (clippedBottom <= clippedTop)
                return;

            context.FillRectangle(color,
                new Rectangle(region.Left, clippedTop, region.Width, clippedBottom - clippedTop));
        }

        private void DrawPanel(RenderContext context, List<(string Text, Color Color)> lines,
                               int x, int y, RenderFont font, RenderFont? headerFont = null)
        {
            headerFont ??= _boldFont;

            var lineHeight = context.MeasureString("Xg", font).Height + 2;
            var width = lines.Max(l => context.MeasureString(l.Text, headerFont).Width) + 14;
            var height = (lineHeight * lines.Count) + 10;

            var box = new Rectangle(x, y, width, height);
            context.FillRectangle(Color.FromArgb(215, 12, 14, 18), box);
            context.DrawRectangle(new RenderPen(Color.FromArgb(120, 140, 150, 170), 1), box);

            var cursor = y + 5;
            for (var i = 0; i < lines.Count; i++)
            {
                var useFont = i == 0 ? headerFont : font;
                context.DrawString(lines[i].Text, useFont, lines[i].Color, x + 7, cursor);
                cursor += lineHeight;
            }
        }

        private void DrawBoxedText(RenderContext context, string text, Color color, int x, int y)
        {
            DrawPanel(context, new List<(string, Color)> { (text, color) }, x, y, _font);
        }

        #endregion

        #region Helpers

        private int FindClockBar(Trade trade, string clock)
        {
            if (!TimeSpan.TryParse(clock, CultureInfo.InvariantCulture, out var at)) return -1;
            return FindBarByNyTime(trade.Session, new TimeSpan(at.Hours, at.Minutes, 0));
        }

        private bool IsClockVisible(Trade? trade, string? clock)
        {
            if (trade == null || string.IsNullOrEmpty(clock)) return false;
            var bar = FindClockBar(trade, clock);
            return bar >= 0 && IsNearVisible(bar);
        }

        // A reconstructed bracket is a review aid, never the historical stop order.
        // Only the last fully closed minute before the recorded entry is used. This
        // proxy must still be verified against the trader's original signal candle.
        private void ResolveHistoricalContext(Trade trade, int signalBar)
        {
            if (!trade.Source.Contains("LUCID", StringComparison.OrdinalIgnoreCase)
                || trade.ChartContextResolved || !ReconstructHistoricalBracket) return;

            var orBar = FindBarByNyTime(trade.Session, new TimeSpan(9, 30, 0));
            if (orBar < 0 || signalBar < 0) return;
            var tick = GetTickSize();
            decimal Label(decimal price) => HistoricalBracketMath.UpperLabel(price, tick);
            var opening = GetCandle(orBar);
            trade.OrHigh = Label(opening.High);
            trade.OrLow = Label(opening.Low);
            trade.Stop = trade.Target = trade.RiskTicks = trade.NetR = 0m;
            trade.BracketSource = "unknown";
            trade.SignalSource = "last_closed_proxy";
            trade.Imbalances.Clear();

            var candle = GetCandle(signalBar);
            var levels = new List<(decimal Price, decimal Bid, decimal Ask)>();
            try
            {
                foreach (var level in candle.GetAllPriceLevels())
                {
                    levels.Add((level.Price, level.Bid, level.Ask));
                }
            }
            catch
            {
                return;
            }
            if (levels.Count == 0) return;
            var result = HistoricalBracketMath.Calculate(levels, candle.High, candle.Low,
                trade.Entry, trade.Direction, tick);
            trade.ChartContextResolved = true;
            if (!result.Success)
            {
                trade.BracketSource = "unknown_atas_proxy_" + result.Reason;
                SaveHistoricalContext(trade, candle.Time, candle.Open, candle.High, candle.Low, candle.Close, levels, result);
                return;
            }
            trade.Imbalances.AddRange(result.Levels.Select(r => new ImbalanceRow
            {
                Low = r.Low, High = r.High, Volume = (int)r.Volume, Reference = (int)r.Reference,
                Ratio = double.IsPositiveInfinity(r.Ratio) ? 999m : (decimal)r.Ratio,
            }));
            trade.Stop = result.Stop;
            trade.Target = result.Target;
            trade.RiskTicks = result.RiskTicks;
            trade.BracketSource = "reconstructed_atas_last_closed_proxy";
            SaveHistoricalContext(trade, candle.Time, candle.Open, candle.High, candle.Low, candle.Close, levels, result);
        }

        private void SaveHistoricalContext(Trade trade, DateTime chartTime,
            decimal open, decimal high, decimal low, decimal close,
            List<(decimal Price, decimal Bid, decimal Ask)> levels, HistoricalBracketMath.Result bracket)
        {
            try
            {
                var directory = Path.Combine(Path.GetDirectoryName(ViewStatePath)!, "historical_journal_footprints", _csvSha256);
                Directory.CreateDirectory(directory);
                var path = Path.Combine(directory, $"{trade.Session:yyyy-MM-dd}_trade{trade.N:000}.json");
                var evidence = new
                {
                    schema = "atas_historical_context_v1", captured_utc = DateTime.UtcNow,
                    source_kind = "atas_candle_price_levels", csv_sha256 = _csvSha256,
                    trade_n = trade.N, group_key = trade.GroupKey,
                    chart_instrument = InstrumentInfo?.Instrument, chart_to_ny_offset_hours = ChartToNyOffsetHours,
                    chart_candle_start = chartTime, ny_candle_start = ToNy(chartTime),
                    signal_candle_source = trade.SignalSource, historical_signal_verified = false,
                    historical_initial_orders_available = false, bracket_source = trade.BracketSource,
                    entry_weighted = trade.Entry, or_high = trade.OrHigh, or_low = trade.OrLow,
                    open, high, low, close,
                    levels = levels.Select(r => new { price = r.Price, bid = r.Bid, ask = r.Ask }).ToArray(),
                    aligned_rows = bracket.Levels.Select(r => new { low = r.Low, high = r.High,
                        volume = r.Volume, reference = r.Reference }).ToArray(),
                    stop = bracket.Stop, target = bracket.Target, risk_ticks = bracket.RiskTicks,
                    bracket_reason = bracket.Reason,
                };
                var json = System.Text.Json.JsonSerializer.Serialize(evidence,
                    new System.Text.Json.JsonSerializerOptions { WriteIndented = true });
                File.WriteAllText(path + ".tmp", json);
                File.Move(path + ".tmp", path, true);
                trade.ContextEvidencePath = path;
            }
            catch { /* Drawing remains available; the view exposes an empty evidence path. */ }
        }

        private void DrawRealExits(RenderContext context, Trade trade, Rectangle region)
        {
            var fills = trade.Fills;
            foreach (var fill in fills)
            {
                var bar = FindClockBar(trade, fill.ExitClock);
                if (bar < 0 || !IsNearVisible(bar)) continue;
                var x = Chart.GetXByBar(bar, true);
                var y = Chart.GetYByPrice(fill.Exit, true);
                if (y < region.Top || y > region.Bottom) continue;
                context.DrawLine(new RenderPen(Color.Cyan, 2), x - 4, y, x + 10, y);
                var entryBar = FindClockBar(trade, fill.EntryClock);
                if (entryBar >= 0 && IsNearVisible(entryBar))
                {
                    var entryX = Chart.GetXByBar(entryBar, true);
                    var entryY = Chart.GetYByPrice(fill.Entry, true);
                    if (entryY >= region.Top && entryY <= region.Bottom)
                        context.DrawLine(new RenderPen(Color.White, 2), entryX - 4, entryY, entryX + 10, entryY);
                }
            }
        }

        private void DrawJournalCaption(RenderContext context, Trade trade, Rectangle region)
        {
            var average = trade.Fills.Select(f => f.Entry).Distinct().Count() > 1 ? "media " : "";
            var text = $"Lucid #{trade.N}/{_trades.Count}  {trade.Session:yyyy-MM-dd}  " +
                $"{(trade.Direction > 0 ? "COMPRA" : "VENTA")} {average}{Fmt(trade.Entry)}  {trade.EntryClock} NY  " +
                $"{trade.Qty} contratos  {trade.NetUsd:+0;-0;0} USD (comision no registrada)";
            var bracket = trade.BracketSource.StartsWith("reconstructed", StringComparison.OrdinalIgnoreCase)
                ? "SL/TP reconstruidos con imbalance de ultima vela cerrada; senal historica pendiente de verificar. Marcas cyan: salidas reales."
                : "SL/TP originales no disponibles; sin imbalance util en vela proxy. Caja: entrada a salida real. Marcas cyan: salidas reales.";
            var lines = new List<(string Text, Color Color)>
            {
                (text, Color.White), (bracket, Color.Orange),
            };
            var height = 2 * (context.MeasureString("Xg", _font).Height + 2) + 10;
            DrawPanel(context, lines, region.Left + 6, region.Bottom - height - 5, _font);
        }

        private IChart Chart => ChartInfo!;

        // Linear scan from the end: the signal candle is always in the first minutes of
        // the session, and replay charts hold a single session, so this stays cheap.
        private int FindBarByNyTime(DateTime session, TimeSpan timeOfDay)
        {
            var wanted = session.Add(timeOfDay);

            for (var bar = CurrentBar - 1; bar >= 0; bar--)
            {
                var ny = ToNy(GetCandle(bar).Time);
                if (ny == wanted)
                    return bar;
                if (ny < wanted.AddHours(-2))
                    break;
            }

            return -1;
        }

        private bool IsNearVisible(int bar)
        {
            var container = Chart.PriceChartContainer;
            return bar >= container.FirstVisibleBarNumber - 1 && bar <= container.LastVisibleBarNumber + 1;
        }

        private decimal GetTickSize()
        {
            var tickSize = InstrumentInfo?.TickSize ?? 0m;
            return tickSize > 0 ? tickSize : FallbackTickSize;
        }

        private static string Fmt(decimal price) =>
            price.ToString("0.00", CultureInfo.InvariantCulture);

        #endregion
    }
}
