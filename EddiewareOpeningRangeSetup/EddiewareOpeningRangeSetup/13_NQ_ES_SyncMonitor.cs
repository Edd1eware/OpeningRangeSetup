using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Linq;
using ATAS.DataFeedsCore;
using OFT.Rendering.Context;
using OFT.Rendering.Tools;

namespace ATAS.Indicators
{
    // Compares the chart instrument (NQ) against ES, both fed by ATAS.
    //
    // ES arrives through the file bridge published by EsFeedPublisher, which must be
    // attached to an ES M1 chart: an ATAS indicator can only observe its own chart's
    // instrument, so there is no in-process way to read a second symbol.
    //
    // NQ and ES do not quote the same number, so ES is converted into NQ points with a
    // rolling ratio (median of NQ close / ES close) before any structural comparison.
    // The monitor reports four regimes: synchronized, one side leading, a measurable
    // lag, or an outright divergence of the two structures.
    [DisplayName("NQ vs ES Structural Sync")]
    public class NqEsStructuralSyncMonitor : Indicator
    {
        private const string TelegramSeries = "nq_es_structural_sync";
        private const int TelegramAlertCopies = 1;

        private const string StatusNqNoData = "NQ SIN DATOS";
        private const string StatusEsNoData = "ES SIN DATOS";
        private const string StatusNqFeedOk = "NQ FEED OK";
        private const string StatusEsFeedOk = "ES FEED OK";
        private const string StatusBeforeWeekStart = "SEMANA NO INICIADA";
        private const string StatusLoading = "CARGANDO ESTRUCTURA M1";
        private const string StatusNqLeads = "NQ LIDERA";
        private const string StatusEsLeads = "ES LIDERA";
        private const string StatusDivergence = "DIVERGENCIA NQ/ES";
        private const string StatusLag = "DESFASE NQ/ES";
        private const string StatusSync = "EN SINCRONÍA";

        private const string SessionCash = "SESION CASH";
        private const string SessionOvernight = "SESION OVERNIGHT";
        private const string SessionOvernightPending = "OVERNIGHT SIN MOVIMIENTO";

        private const string NqName = "NQ";
        private const string EsName = "ES";

        private static readonly TimeZoneInfo NewYorkTimeZone = ResolveNewYorkTimeZone();

        private readonly object _sync = new();
        private readonly SortedDictionary<decimal, decimal> _bids = new();
        private readonly SortedDictionary<decimal, decimal> _asks = new();
        private readonly SortedDictionary<DateTime, StructuralBar> _nqBars = new();
        private readonly SortedDictionary<DateTime, StructuralBar> _esBars = new();
        private readonly HashSet<string> _sentAlertSignatures = new(StringComparer.Ordinal);
        private readonly Queue<string> _sentAlertOrder = new();
        private const float DefaultSessionFontSize = 28f;
        private readonly LiquidityBurstDetector _liquidityBurstDetector;

        private TimeSpan _timerPeriod;
        private bool _timerSubscribed;
        private int _monitorTickRunning;
        private DateTime _lastNqArrivalUtc;
        private DateTime _lastEsPriceUtc;
        private DateTime _lastEsHistoryUtc;
        private DateTime _lastHistoryReadAttemptUtc;
        private DateTime _lastStructuralCheckUtc;
        private DisplayAwakeGuard? _displayAwakeGuard;
        private decimal _bestBid;
        private decimal _bestAsk;
        private decimal _nqMid;
        private decimal _lastNqTrade;
        private decimal _esBid;
        private decimal _esAsk;
        private decimal _esMid;
        private decimal _esLast;
        private long _esSequence = -1;
        private long _esTickTimeMsc;
        private string _esSymbol = "";
        private double _lastScaleRatio;
        private string _displayStatus = "INICIANDO";
        private string _displayDetail = "Esperando velas M1 de NQ y del puente ES";
        private string _displayPrices = "";
        private Color _displayColor = Color.Gold;
        private string _lastError = "";
        private string _sessionLabel = "";
        private Color _sessionColor = Color.Gold;
        private RenderFont _sessionFont = new("Arial", DefaultSessionFontSize);
        private float _sessionFontSizeInUse = DefaultSessionFontSize;
        private DateTime _overnightMoveDay = DateTime.MinValue;
        private DateTime _lastSessionCandleMinute = DateTime.MinValue;

        [Display(Name = "Archivo precio ES", Order = 1, GroupName = "Conexión")]
        public string EsPriceFile { get; set; } =
            Path.Combine(EsFeedPublisher.DefaultFolder, EsFeedPublisher.DefaultPriceFile);

        [Display(Name = "Historial M1 ES", Order = 2, GroupName = "Conexión")]
        public string EsHistoryFile { get; set; } =
            Path.Combine(EsFeedPublisher.DefaultFolder, EsFeedPublisher.DefaultHistoryFile);

        [Display(Name = "Carpeta Telegram", Order = 3, GroupName = "Conexión")]
        public string TelegramFolder { get; set; } =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score";

        [Display(Name = "Carpeta de diagnóstico", Order = 4, GroupName = "Conexión")]
        public string OutputFolder { get; set; } =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\nq_es_sync";

        [Range(3, 10)]
        [Display(Name = "Desfase mínimo líder (velas)", Order = 11, GroupName = "Estructura M1")]
        public int MinimumLeadCandles { get; set; } = 3;

        [Range(3, 20)]
        [Display(Name = "Desfase máximo buscado (velas)", Order = 12, GroupName = "Estructura M1")]
        public int MaximumLeadCandles { get; set; } = 8;

        [Range(12, 120)]
        [Display(Name = "Velas mínimas de análisis", Order = 13, GroupName = "Estructura M1")]
        public int MinimumCompletedCandles { get; set; } = 24;

        [Range(20, 240)]
        [Display(Name = "Ventana estructural (velas)", Order = 14, GroupName = "Estructura M1")]
        public int StructuralWindowCandles { get; set; } = 60;

        [Range(2, 4)]
        [Display(Name = "Fuerza pivote izquierda/derecha", Order = 15, GroupName = "Estructura M1")]
        public int PivotStrength { get; set; } = 2;

        [Range(4, 20)]
        [Display(Name = "Lookback del swing", Order = 16, GroupName = "Estructura M1")]
        public int PivotSwingLookback { get; set; } = 20;

        [Range(0.5, 10.0)]
        [Display(Name = "Swing mínimo (ATR)", Order = 17, GroupName = "Estructura M1")]
        public double MinimumPivotSwingAtr { get; set; } = 5.0;

        [Range(0.25, 5.0)]
        [Display(Name = "Reacción mínima (ATR)", Order = 18, GroupName = "Estructura M1")]
        public double MinimumPivotReactionAtr { get; set; } = 1.5;

        [Range(1, 30)]
        [Display(Name = "Datos vencidos después de (s)", Order = 19, GroupName = "Estructura M1")]
        public int StaleAfterSeconds { get; set; } = 3;

        [Range(50, 1000)]
        [Display(Name = "Lectura del puente (ms)", Order = 20, GroupName = "Estructura M1")]
        public int SampleIntervalMilliseconds { get; set; } = 100;

        [Range(1, 60)]
        [Display(Name = "Vigencia Liquidity Burst (s)", Order = 21, GroupName = "Estructura M1")]
        public int LiquidityBurstMaxAgeSeconds { get; set; } = 10;

        [Range(20, 240)]
        [Display(Name = "Ventana de escala NQ/ES (velas)", Order = 30, GroupName = "Conversión ES→NQ")]
        public int ScaleWindowCandles { get; set; } = 60;

        [Range(0.0, 1.0)]
        [Display(Name = "Correlación mínima de sincronía", Order = 31, GroupName = "Conversión ES→NQ")]
        public double MinimumSyncCorrelation { get; set; } = 0.55;

        [Range(1.0, 6.0)]
        [Display(Name = "Divergencia: |z| del spread", Order = 32, GroupName = "Conversión ES→NQ")]
        public double DivergenceSpreadZ { get; set; } = 2.5;

        [Display(Name = "Telegram también en divergencia", Order = 33, GroupName = "Conversión ES→NQ")]
        public bool AlertOnDivergence { get; set; } = false;

        // Off by default: the Telegram alert moved to the MT5 side (StructuralLeadSync),
        // because no ATAS instrument was found to pair against the SP500 CFD. The sending
        // code stays intact so flipping this back on is enough to restore it.
        [Display(Name = "Enviar alertas a Telegram", Order = 39, GroupName = "Alertas")]
        public bool EnableTelegram { get; set; } = false;

        // ES has no meaningful session before the week opens, so any lead read over that
        // stretch is noise: neither side can legitimately lead. Suppress the verdict itself,
        // not just the Telegram alert.
        [Display(Name = "Sin liderazgo ni Telegram hasta el inicio de semana", Order = 40, GroupName = "Alertas")]
        public bool MuteBeforeWeekStart { get; set; } = true;

        [Display(Name = "Inicio de semana ES (lunes, hora NY)", Order = 41, GroupName = "Alertas")]
        public TimeSpan WeekStartNy { get; set; } = new TimeSpan(9, 30, 0);

        [Display(Name = "Apertura cash (hora NY)", Order = 50, GroupName = "Sesión")]
        public TimeSpan CashOpenNy { get; set; } = new TimeSpan(9, 30, 0);

        // Only the earliest instant an overnight candle can count: the label does NOT
        // flip at this clock time, it waits for the first M1 candle that actually moved.
        [Display(Name = "Cierre cash / inicio overnight (hora NY)", Order = 51, GroupName = "Sesión")]
        public TimeSpan CashCloseNy { get; set; } = new TimeSpan(16, 0, 0);

        [Range(0.0, 100.0)]
        [Display(Name = "Rango mínimo de vela para contar movimiento (puntos)", Order = 52, GroupName = "Sesión")]
        public double SessionMoveMinimumRange { get; set; } = 0.0;

        [Range(8.0, 72.0)]
        [Display(Name = "Tamaño de fuente de la sesión", Order = 53, GroupName = "Sesión")]
        public float SessionFontSize { get; set; } = DefaultSessionFontSize;

        // Where the text starts, measured from the left edge of the panel. This clears the
        // cursor-counter box, whose width does not depend on how wide the chart is: an
        // offset from the center would drift over the box every time the window resizes.
        // 0 falls back to centering plus SessionOffsetX.
        [Range(0, 2000)]
        [Display(Name = "Inicio del texto (px desde el borde izquierdo, 0 = centrado)", Order = 54, GroupName = "Sesión")]
        public int SessionStartX { get; set; } = 590;

        [Range(-1200, 1200)]
        [Display(Name = "Desplazamiento horizontal si va centrado (px)", Order = 56, GroupName = "Sesión")]
        public int SessionOffsetX { get; set; } = 0;

        [Range(0, 400)]
        [Display(Name = "Desplazamiento vertical (px desde arriba)", Order = 55, GroupName = "Sesión")]
        public int SessionOffsetY { get; set; } = 12;

        public NqEsStructuralSyncMonitor()
        {
            Name = "NQ vs ES Structural Sync";
            DenyToChangePanel = true;
            EnableCustomDrawing = true;
            SubscribeToDrawingEvents(DrawingLayouts.LatestBar);

            // Run the causal one-second tape detector as a child so the Telegram
            // alert does not depend on a second indicator being added manually.
            _liquidityBurstDetector = new LiquidityBurstDetector
            {
                ExportCsv = false,
                GateByTargetDate = false,
                UseCandleFallback = false
            };
            Add(_liquidityBurstDetector);

            // The detector exists only to enrich the alert, so keep it out of the
            // chart legend: hiding every series drops its entry, and the tape
            // callbacks it depends on keep firing regardless of what is drawn.
            _liquidityBurstDetector.ShowDescription = false;
            foreach (var series in _liquidityBurstDetector.DataSeries)
            {
                series.IsHidden = true;
                series.ShowTooltip = false;
                series.ShowNameOnMouseOver = false;
            }
        }

        protected override void OnInitialize()
        {
            base.OnInitialize();

            // This monitor is intentionally calibrated to the user's setup:
            // A leader must already have a confirmed structure while the other
            // market still has none after at least three completed M1 bars.
            MinimumLeadCandles = 3;
            PivotStrength = 2;
            PivotSwingLookback = 20;
            MinimumPivotSwingAtr = 5.0;
            MinimumPivotReactionAtr = 1.5;
            _displayAwakeGuard = new DisplayAwakeGuard();
            SeedMarketDepth();
            _timerPeriod = TimeSpan.FromMilliseconds(Math.Clamp(SampleIntervalMilliseconds, 50, 1000));
            SubscribeToTimer(_timerPeriod, MonitorTick);
            _timerSubscribed = true;
        }

        protected override void OnDispose()
        {
            if (_timerSubscribed)
            {
                try { UnsubscribeFromTimer(_timerPeriod, MonitorTick); }
                catch { }
                _timerSubscribed = false;
            }

            _displayAwakeGuard?.Dispose();
            _displayAwakeGuard = null;

            base.OnDispose();
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            try
            {
                var candle = GetCandle(bar);
                var minute = FloorMinute(ToUtc(candle.Time));
                var structuralBar = new StructuralBar(
                    minute,
                    (double)candle.Open,
                    (double)candle.High,
                    (double)candle.Low,
                    (double)candle.Close);

                if (!structuralBar.IsValid)
                    return;

                lock (_sync)
                {
                    _nqBars[minute] = structuralBar;
                    TrimBars(_nqBars, 360);
                    TrackOvernightCandle(structuralBar);
                }
            }
            catch (Exception ex)
            {
                lock (_sync)
                    _lastError = "nq_candle:" + ex.GetType().Name;
            }
        }

        protected override void MarketDepthChanged(MarketDataArg depth)
        {
            base.MarketDepthChanged(depth);
            ApplyDepth(depth, DateTime.UtcNow);
        }

        protected override void MarketDepthsChanged(IEnumerable<MarketDataArg> depths)
        {
            base.MarketDepthsChanged(depths);
            if (depths == null)
                return;

            var now = DateTime.UtcNow;
            foreach (var depth in depths)
                ApplyDepth(depth, now);
        }

        protected override void OnNewTrade(MarketDataArg trade)
        {
            base.OnNewTrade(trade);
            if (trade == null)
                return;

            lock (_sync)
                _lastNqTrade = trade.Price;
        }

        protected override void OnRender(RenderContext context, DrawingLayouts layout)
        {
            if (Container == null)
                return;

            var region = Container.Region;
            string session;
            Color sessionColor;

            lock (_sync)
            {
                session = _sessionLabel;
                sessionColor = _sessionColor;
            }

            // Only the session label is drawn. The feed status, the M1/age line and the
            // price/ratio line still run and still reach the CSV and the alerts: they were
            // dropped from the chart, not from the monitor.
            // Rebuilt only when the setting actually changes: allocating a font on every
            // frame would churn GDI handles at the timer's redraw rate.
            var size = Math.Clamp(SessionFontSize, 8f, 72f);
            if (Math.Abs(size - _sessionFontSizeInUse) > 0.01f)
            {
                _sessionFont = new RenderFont("Arial", size);
                _sessionFontSizeInUse = size;
            }

            if (string.IsNullOrEmpty(session))
                return;

            var y = region.Top + SessionOffsetY;

            if (SessionStartX > 0)
            {
                context.DrawString(session, _sessionFont, sessionColor, region.Left + SessionStartX, y);
                return;
            }

            DrawCentered(context, session, _sessionFont, sessionColor, region, y, SessionOffsetX);
        }

        private static void DrawCentered(
            RenderContext context,
            string text,
            RenderFont font,
            Color color,
            Rectangle region,
            int y,
            int offsetX = 0)
        {
            if (string.IsNullOrEmpty(text))
                return;

            var width = context.MeasureString(text, font).Width;
            var x = region.Left + ((region.Width - width) / 2) + offsetX;
            if (x < region.Left)
                x = region.Left;

            context.DrawString(text, font, color, x, y);
        }

        private void SeedMarketDepth()
        {
            try
            {
                var now = DateTime.UtcNow;
                foreach (var depth in GetMarketDepthSnapshot())
                    ApplyDepth(depth, now);
            }
            catch (Exception ex)
            {
                lock (_sync)
                    _lastError = "depth_snapshot:" + ex.GetType().Name;
            }
        }

        private void ApplyDepth(MarketDataArg? depth, DateTime arrivalUtc)
        {
            if (depth == null)
                return;

            lock (_sync)
            {
                SortedDictionary<decimal, decimal>? book = null;
                if (depth.DataType == MarketDataType.Bid)
                    book = _bids;
                else if (depth.DataType == MarketDataType.Ask)
                    book = _asks;

                if (book == null)
                    return;

                if (depth.Volume <= 0)
                    book.Remove(depth.Price);
                else
                    book[depth.Price] = depth.Volume;

                _bestBid = _bids.Count == 0 ? 0 : _bids.Last().Key;
                _bestAsk = _asks.Count == 0 ? 0 : _asks.First().Key;
                if (_bestBid > 0 && _bestAsk > 0 && _bestBid <= _bestAsk)
                {
                    _nqMid = (_bestBid + _bestAsk) / 2m;
                    UpdateLiveNqBar(arrivalUtc, (double)_nqMid);
                }

                _lastNqArrivalUtc = arrivalUtc;
            }
        }

        private void UpdateLiveNqBar(DateTime utc, double price)
        {
            var minute = FloorMinute(utc);
            if (_nqBars.TryGetValue(minute, out var current))
                _nqBars[minute] = current.Update(price);
            else
                _nqBars[minute] = new StructuralBar(minute, price, price, price, price);
        }

        private void MonitorTick()
        {
            if (System.Threading.Interlocked.Exchange(ref _monitorTickRunning, 1) != 0)
                return;

            try
            {
                var now = DateTime.UtcNow;
                ReadEsPrice();
                if (now - _lastHistoryReadAttemptUtc >= TimeSpan.FromSeconds(2))
                {
                    _lastHistoryReadAttemptUtc = now;
                    ReadEsHistory();
                }

                var checkStructure = false;
                lock (_sync)
                {
                    UpdateLiveDisplay(now);
                    if (now - _lastStructuralCheckUtc >= TimeSpan.FromSeconds(2))
                    {
                        _lastStructuralCheckUtc = now;
                        checkStructure = true;
                    }
                }

                if (checkStructure)
                    CheckImmediateAlert(now);

                RedrawChart();
            }
            catch (Exception ex)
            {
                lock (_sync)
                {
                    _lastError = "monitor:" + ex.GetType().Name;
                    _displayStatus = "ERROR DE MONITOR";
                    _displayDetail = _lastError;
                    _displayColor = Color.OrangeRed;
                }
            }
            finally
            {
                System.Threading.Volatile.Write(ref _monitorTickRunning, 0);
            }
        }

        private void ReadEsPrice()
        {
            try
            {
                if (!File.Exists(EsPriceFile))
                    return;

                var fields = ReadAllTextShared(EsPriceFile).Trim().Split(';');
                if (fields.Length < 8 || !string.Equals(fields[0], EsFeedPublisher.PriceVersion, StringComparison.Ordinal))
                    return;

                if (!decimal.TryParse(fields[2], NumberStyles.Float, CultureInfo.InvariantCulture, out var bid) ||
                    !decimal.TryParse(fields[3], NumberStyles.Float, CultureInfo.InvariantCulture, out var ask) ||
                    !decimal.TryParse(fields[4], NumberStyles.Float, CultureInfo.InvariantCulture, out var last) ||
                    !long.TryParse(fields[5], NumberStyles.Integer, CultureInfo.InvariantCulture, out var tickTimeMsc) ||
                    !long.TryParse(fields[6], NumberStyles.Integer, CultureInfo.InvariantCulture, out var sequence))
                {
                    return;
                }

                if (bid <= 0 && ask <= 0 && last <= 0)
                    return;

                lock (_sync)
                {
                    if (sequence == _esSequence)
                        return;

                    _esSequence = sequence;
                    _esSymbol = fields[1];
                    _esBid = bid;
                    _esAsk = ask;
                    _esLast = last;
                    _esMid = bid > 0 && ask > 0 && bid <= ask ? (bid + ask) / 2m : last;
                    _esTickTimeMsc = tickTimeMsc;
                    _lastEsPriceUtc = File.GetLastWriteTimeUtc(EsPriceFile);
                    _lastError = "";
                }
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException)
            {
                lock (_sync)
                    _lastError = "es_price:access_denied";
            }
            catch (Exception ex)
            {
                lock (_sync)
                    _lastError = "es_price:" + ex.GetType().Name;
            }
        }

        private void ReadEsHistory()
        {
            try
            {
                if (!File.Exists(EsHistoryFile))
                    return;

                var lines = ReadAllLinesShared(EsHistoryFile);
                if (lines.Length < 3)
                    return;

                var header = lines[0].Split(';');
                if (header.Length < 2 || !string.Equals(header[0], EsFeedPublisher.HistoryVersion, StringComparison.Ordinal))
                    return;

                var parsed = new SortedDictionary<DateTime, StructuralBar>();
                for (var index = 1; index < lines.Length; index++)
                {
                    var fields = lines[index].Split(';');
                    if (fields.Length < 5 ||
                        !long.TryParse(fields[0], NumberStyles.Integer, CultureInfo.InvariantCulture, out var utcSeconds) ||
                        !double.TryParse(fields[1], NumberStyles.Float, CultureInfo.InvariantCulture, out var open) ||
                        !double.TryParse(fields[2], NumberStyles.Float, CultureInfo.InvariantCulture, out var high) ||
                        !double.TryParse(fields[3], NumberStyles.Float, CultureInfo.InvariantCulture, out var low) ||
                        !double.TryParse(fields[4], NumberStyles.Float, CultureInfo.InvariantCulture, out var close))
                    {
                        continue;
                    }

                    var minute = DateTimeOffset.FromUnixTimeSeconds(utcSeconds).UtcDateTime;
                    var bar = new StructuralBar(FloorMinute(minute), open, high, low, close);
                    if (bar.IsValid)
                        parsed[bar.UtcMinute] = bar;
                }

                if (parsed.Count < 3)
                    return;

                lock (_sync)
                {
                    _esBars.Clear();
                    foreach (var item in parsed)
                        _esBars[item.Key] = item.Value;
                    TrimBars(_esBars, 360);
                    _esSymbol = header[1];
                    _lastEsHistoryUtc = File.GetLastWriteTimeUtc(EsHistoryFile);
                }
            }
            catch (IOException) { }
            catch (Exception ex)
            {
                lock (_sync)
                    _lastError = "es_history:" + ex.GetType().Name;
            }
        }

        private void UpdateLiveDisplay(DateTime now)
        {
            var nqAge = AgeMilliseconds(now, _lastNqArrivalUtc);
            var esAge = AgeMilliseconds(now, _lastEsPriceUtc);
            var staleMs = Math.Max(1, StaleAfterSeconds) * 1000L;

            var nqOk = _nqMid > 0 && nqAge <= staleMs;
            var esOk = _esMid > 0 && esAge <= staleMs;

            if (!nqOk || !esOk)
            {
                _displayStatus = BuildFeedStatus(nqOk, esOk);
                _displayColor = Color.OrangeRed;
            }
            else if (IsBeforeWeekStart(now))
            {
                _displayStatus = StatusBeforeWeekStart;
                _displayColor = Color.Gold;
            }
            else if (_nqBars.Count < MinimumCompletedCandles || _esBars.Count < MinimumCompletedCandles)
            {
                _displayStatus = StatusLoading;
                _displayColor = Color.Gold;
            }

            UpdateSessionLabel(now);

            _displayDetail = $"M1 NQ={_nqBars.Count} ES={_esBars.Count} | edad NQ={nqAge} ms ES={esAge} ms";
            if (!string.IsNullOrWhiteSpace(_lastError))
                _displayDetail += " | " + _lastError;
            _displayPrices = BuildPricesLine(_lastScaleRatio);
        }

        // Always names BOTH feeds so a stale side is never mistaken for a total outage:
        // "ES SIN DATOS | NQ FEED OK" tells you at a glance which half of the bridge broke.
        private static string BuildFeedStatus(bool nqOk, bool esOk)
        {
            if (!nqOk && !esOk)
                return StatusNqNoData + " | " + StatusEsNoData;

            if (!nqOk)
                return StatusNqNoData + " | " + StatusEsFeedOk;

            if (!esOk)
                return StatusEsNoData + " | " + StatusNqFeedOk;

            return StatusSync;
        }

        private static string BuildFeedDetail(bool nqOk, bool esOk, long nqAge, long esAge)
        {
            if (!nqOk && !esOk)
                return $"Sin movimiento NQ ({nqAge} ms) ni ES ({esAge} ms)";

            if (!nqOk)
                return $"Sin movimiento NQ: última llegada L2 hace {nqAge} ms | ES vivo ({esAge} ms)";

            return $"Sin movimiento ES: puente hace {esAge} ms (¿publicador ES adjunto?) | NQ vivo ({nqAge} ms)";
        }

        private string BuildPricesLine(double ratio)
        {
            var esMidInNq = ratio > 0 ? (double)_esMid * ratio : 0;
            return string.Format(
                CultureInfo.InvariantCulture,
                "NQ {0}: {1:0.00}/{2:0.00} | ES {3}: {4:0.00}/{5:0.00} (≈NQ {6:0.00}) | ratio {7:0.0000}",
                Instrument,
                _bestBid,
                _bestAsk,
                string.IsNullOrWhiteSpace(_esSymbol) ? "?" : _esSymbol,
                _esBid,
                _esAsk,
                esMidInNq,
                ratio);
        }

        private void CheckImmediateAlert(DateTime now)
        {
            Report report;
            lock (_sync)
                report = BuildReport(now);

            var isLead = report.Status == StatusNqLeads || report.Status == StatusEsLeads;
            var isDivergence = report.Status == StatusDivergence;
            var alertable = isLead || (isDivergence && AlertOnDivergence);
            var muted = IsBeforeWeekStart(now);
            var shouldAlert = false;
            var signature = $"{report.Status}|{report.PivotKind}|{report.LeaderPivotMinute:O}|{report.LaggerPivotMinute:O}";
            lock (_sync)
            {
                _displayStatus = report.Status;
                _displayDetail = report.Detail;
                _displayPrices = report.Prices;
                _displayColor = report.Color;

                if (alertable && !muted && !_sentAlertSignatures.Contains(signature))
                {
                    _sentAlertSignatures.Add(signature);
                    _sentAlertOrder.Enqueue(signature);
                    while (_sentAlertOrder.Count > 256)
                        _sentAlertSignatures.Remove(_sentAlertOrder.Dequeue());
                    shouldAlert = true;
                }
            }

            if (shouldAlert)
                ProduceAlert(now, report);
        }

        // Marks the overnight session as started only when a real M1 candle printed
        // after the cash close. The clock alone never flips the label: a candle whose
        // high equals its low is a frozen feed, not a session, so it does not count.
        private void TrackOvernightCandle(StructuralBar bar)
        {
            // Older bars only arrive on history reloads and must not rewind the state.
            // The current minute is re-evaluated on every update because its first tick
            // always has high == low: the movement only shows up on later updates.
            if (bar.UtcMinute < _lastSessionCandleMinute)
                return;

            _lastSessionCandleMinute = bar.UtcMinute;

            var ny = TimeZoneInfo.ConvertTimeFromUtc(bar.UtcMinute, NewYorkTimeZone);
            if (IsCashWindow(ny))
                return;

            var range = bar.High - bar.Low;
            if (range <= 0 || range < SessionMoveMinimumRange)
                return;

            _overnightMoveDay = OvernightDayKey(ny);
        }

        private bool IsCashWindow(DateTime ny)
        {
            return ny.DayOfWeek != DayOfWeek.Saturday
                && ny.DayOfWeek != DayOfWeek.Sunday
                && ny.TimeOfDay >= CashOpenNy
                && ny.TimeOfDay < CashCloseNy;
        }

        // One overnight stretch spans two calendar days, so both halves must resolve to
        // the same key: everything before the cash open belongs to the previous day.
        private DateTime OvernightDayKey(DateTime ny)
        {
            return ny.TimeOfDay < CashOpenNy ? ny.Date.AddDays(-1) : ny.Date;
        }

        private void UpdateSessionLabel(DateTime now)
        {
            var ny = TimeZoneInfo.ConvertTimeFromUtc(
                now.Kind == DateTimeKind.Utc ? now : now.ToUniversalTime(),
                NewYorkTimeZone);

            if (IsCashWindow(ny))
            {
                _sessionLabel = SessionCash;
                _sessionColor = Color.Red;
                return;
            }

            if (_overnightMoveDay == OvernightDayKey(ny))
            {
                _sessionLabel = SessionOvernight;
                _sessionColor = Color.DeepSkyBlue;
                return;
            }

            _sessionLabel = SessionOvernightPending;
            _sessionColor = Color.Gold;
        }

        // Silent from Sunday 00:00 NY until the ES week opens on Monday. The on-screen
        // status keeps updating: only Telegram is held back.
        private bool IsBeforeWeekStart(DateTime now)
        {
            if (!MuteBeforeWeekStart)
                return false;

            var ny = TimeZoneInfo.ConvertTimeFromUtc(
                now.Kind == DateTimeKind.Utc ? now : now.ToUniversalTime(),
                NewYorkTimeZone);

            return ny.DayOfWeek switch
            {
                DayOfWeek.Sunday => true,
                DayOfWeek.Monday => ny.TimeOfDay < WeekStartNy,
                _ => false,
            };
        }

        private void ProduceAlert(DateTime now, Report report)
        {
            // The CSV keeps recording regardless: only the outbound notification is gated,
            // so local diagnostics survive with Telegram off.
            WriteReportCsv(now, "alerta", report);
            if (!EnableTelegram)
                return;

            var caption = BuildTelegramMessage(now, report);
            var screenshot = AtasMt5ComparisonScreenshot.Capture(
                OutputFolder,
                report.Status,
                report.Detail,
                report.Prices);

            if (!string.IsNullOrWhiteSpace(screenshot))
            {
                TelegramTradeNotifier.QueuePhotoAlert(
                    TelegramFolder,
                    TelegramSeries + "_alert",
                    FloorMinute(now),
                    caption,
                    screenshot,
                    TelegramAlertCopies);
                return;
            }

            lock (_sync)
                _lastError = "screenshot_failed";
            TelegramTradeNotifier.QueuePeriodicStatus(
                TelegramFolder,
                TelegramSeries + "_alert_fallback",
                FloorMinute(now),
                caption + Environment.NewLine + "Captura no disponible",
                TelegramAlertCopies);
        }

        private Report BuildReport(DateTime now)
        {
            var nqAge = AgeMilliseconds(now, _lastNqArrivalUtc);
            var esAge = AgeMilliseconds(now, _lastEsPriceUtc);
            var staleMs = Math.Max(1, StaleAfterSeconds) * 1000L;
            var analysis = AnalyzeStructure(now);
            if (analysis.ScaleRatio > 0)
                _lastScaleRatio = analysis.ScaleRatio;

            var expectedSide = analysis.PivotKind == "INFERIOR"
                ? "LONG"
                : analysis.PivotKind == "SUPERIOR" ? "SHORT" : "";
            var expectedLagger = analysis.LeaderName == NqName
                ? EsName
                : analysis.LeaderName == EsName ? NqName : "";
            var nowNy = TimeZoneInfo.ConvertTimeFromUtc(
                now.Kind == DateTimeKind.Utc ? now : now.ToUniversalTime(),
                NewYorkTimeZone);
            var burst = LiquidityBurstSignalBus.GetLatest(
                nowNy.Date,
                now,
                Math.Clamp(LiquidityBurstMaxAgeSeconds, 1, 60));
            var expectedBurstSide = expectedSide == "LONG"
                ? "SELL"
                : expectedSide == "SHORT" ? "BUY" : "";
            var burstAlignment = burst == null || string.IsNullOrWhiteSpace(expectedBurstSide)
                ? "NO DISPONIBLE"
                : string.Equals(burst.Side, expectedBurstSide, StringComparison.OrdinalIgnoreCase)
                    ? "APOYA EL ESCENARIO"
                    : "CONTRADICE EL ESCENARIO";
            var status = StatusSync;
            var detail = analysis.Reason;
            var color = Color.LimeGreen;

            var nqOk = _nqMid > 0 && nqAge <= staleMs;
            var esOk = _esMid > 0 && esAge <= staleMs;

            if (!nqOk || !esOk)
            {
                status = BuildFeedStatus(nqOk, esOk);
                detail = BuildFeedDetail(nqOk, esOk, nqAge, esAge);
                color = Color.OrangeRed;
            }
            else if (IsBeforeWeekStart(now))
            {
                // Before the ES week opens neither side can legitimately lead, so the
                // verdict is withheld rather than reported as a real lead.
                status = StatusBeforeWeekStart;
                detail = $"ES abre el lunes {WeekStartNy:hh\\:mm} NY: sin veredicto de liderazgo";
                color = Color.Gold;
            }
            else if (!analysis.Available)
            {
                status = StatusLoading;
                detail = analysis.Reason;
                color = Color.Gold;
            }
            else if (analysis.Confirmed && analysis.LagCandles >= MinimumLeadCandles)
            {
                status = StatusNqLeads;
                detail = BuildPivotDetail(NqName, analysis);
                color = Color.DeepSkyBlue;
            }
            else if (analysis.Confirmed && analysis.LagCandles <= -MinimumLeadCandles)
            {
                status = StatusEsLeads;
                detail = BuildPivotDetail(EsName, analysis);
                color = Color.Violet;
            }
            else if (analysis.IsDivergent)
            {
                status = StatusDivergence;
                detail = BuildSyncDetail(analysis);
                color = Color.Orange;
            }
            else if (analysis.BestLagCandles != 0 && analysis.BestLagCorrelation >= MinimumSyncCorrelation)
            {
                status = StatusLag;
                detail = BuildSyncDetail(analysis);
                color = Color.Khaki;
            }
            else
            {
                detail = BuildSyncDetail(analysis);
            }

            var prices = BuildPricesLine(analysis.ScaleRatio > 0 ? analysis.ScaleRatio : _lastScaleRatio);

            return new Report(
                status,
                detail,
                prices,
                color,
                analysis.LagCandles,
                analysis.LeaderSwingAtr,
                analysis.LaggerSwingAtr,
                analysis.LeaderReactionAtr,
                analysis.LaggerReactionAtr,
                analysis.ComparedCandles,
                nqAge,
                esAge,
                _bestBid,
                _bestAsk,
                _nqMid,
                _esSymbol,
                _esBid,
                _esAsk,
                _esMid,
                _esLast,
                _esTickTimeMsc,
                analysis.ScaleRatio,
                analysis.NqLastMinute,
                analysis.EsLastMinute,
                analysis.PivotKind,
                analysis.LeaderPivotMinute,
                analysis.LaggerPivotMinute,
                analysis.LeaderName,
                expectedLagger,
                expectedSide,
                analysis.ExpectedLaggerPriceNq,
                analysis.ExpectedLaggerPriceNative,
                analysis.MappingBasis,
                analysis.Correlation,
                analysis.BestLagCandles,
                analysis.BestLagCorrelation,
                analysis.SpreadPoints,
                analysis.SpreadZ,
                analysis.SpreadAtr,
                burst?.BurstId ?? "",
                burst?.Side ?? "",
                burst?.TimestampUtc ?? DateTime.MinValue,
                burst?.Price ?? 0,
                burst?.Delta1s ?? 0,
                burst?.DeltaChangeZScore ?? 0,
                burst?.Velocity1s ?? 0,
                burstAlignment);
        }

        private StructuralAnalysis AnalyzeStructure(DateTime now)
        {
            var currentMinute = FloorMinute(now);
            var strength = Math.Clamp(PivotStrength, 2, 4);
            var swingLookback = Math.Clamp(PivotSwingLookback, 4, 20);
            var maxDelay = Math.Clamp(MaximumLeadCandles, MinimumLeadCandles, 20);
            var take = Math.Clamp(StructuralWindowCandles, 20, 240) + maxDelay + swingLookback + strength + 20;
            var nq = _nqBars.Values.Where(x => x.UtcMinute < currentMinute).TakeLast(take).ToArray();
            var es = _esBars.Values.Where(x => x.UtcMinute < currentMinute).TakeLast(take).ToArray();
            var minimum = Math.Clamp(MinimumCompletedCandles, 12, 120);

            if (nq.Length < minimum || es.Length < minimum)
            {
                return StructuralAnalysis.Unavailable(
                    $"Velas completas NQ={nq.Length}, ES={es.Length}; mínimo={minimum}");
            }

            var nqByMinute = nq.ToDictionary(x => x.UtcMinute);
            var esByMinute = es.ToDictionary(x => x.UtcMinute);
            var alignedNq = new List<StructuralBar>();
            var alignedEs = new List<StructuralBar>();

            // One feed can publish a minute later than the other; start the common
            // stretch at the newest minute both sides already closed.
            var cursor = nq[^1].UtcMinute <= es[^1].UtcMinute ? nq[^1].UtcMinute : es[^1].UtcMinute;
            while (alignedNq.Count < take &&
                   nqByMinute.TryGetValue(cursor, out var nqBar) &&
                   esByMinute.TryGetValue(cursor, out var esBar))
            {
                alignedNq.Add(nqBar);
                alignedEs.Add(esBar);
                cursor = cursor.AddMinutes(-1);
            }

            if (alignedNq.Count < minimum)
            {
                return StructuralAnalysis.Unavailable(
                    $"Hueco M1 detectado; tramo continuo común={alignedNq.Count}, mínimo={minimum}");
            }

            alignedNq.Reverse();
            alignedEs.Reverse();
            var nqAligned = alignedNq.ToArray();
            var esRaw = alignedEs.ToArray();

            // NQ and ES quote different index levels, so the conversion is
            // multiplicative. The median of the close ratio is used instead of the
            // mean because a single stale minute on either feed would drag a mean.
            var scaleWindow = Math.Clamp(ScaleWindowCandles, 20, 240);
            var ratioSamples = new List<double>(scaleWindow);
            for (var index = Math.Max(0, nqAligned.Length - scaleWindow); index < nqAligned.Length; index++)
            {
                if (esRaw[index].Close > 0)
                    ratioSamples.Add(nqAligned[index].Close / esRaw[index].Close);
            }

            var ratio = Median(ratioSamples);
            if (ratio <= 0)
            {
                return StructuralAnalysis.Unavailable("No se pudo estimar la escala NQ/ES");
            }

            var esInNq = new StructuralBar[esRaw.Length];
            for (var index = 0; index < esRaw.Length; index++)
            {
                var bar = esRaw[index];
                esInNq[index] = new StructuralBar(
                    bar.UtcMinute,
                    bar.Open * ratio,
                    bar.High * ratio,
                    bar.Low * ratio,
                    bar.Close * ratio);
            }

            var quality = MeasureSync(nqAligned, esInNq, scaleWindow, maxDelay);
            var isDivergent = quality.Correlation < MinimumSyncCorrelation ||
                              Math.Abs(quality.SpreadZ) >= DivergenceSpreadZ;

            var nqPivots = DetectPivots(nqAligned, strength, swingLookback, 0.50, 0.25);
            var esPivots = DetectPivots(esInNq, strength, swingLookback, 0.50, 0.25);
            var latestComplete = nqAligned[^1].UtcMinute;
            LeaderEvidence? best = null;
            foreach (var pivot in nqPivots)
            {
                if (pivot.SwingAtr < MinimumPivotSwingAtr ||
                    pivot.ReactionAtr < MinimumPivotReactionAtr ||
                    pivot.UtcMinute.AddMinutes(MinimumLeadCandles) != latestComplete ||
                    HasEquivalentPivot(esPivots, pivot, true, nqAligned, esInNq, maxDelay, latestComplete))
                    continue;
                var evidence = new LeaderEvidence(
                    pivot,
                    MinimumLeadCandles,
                    NqName,
                    Math.Min(pivot.SwingAtr / MinimumPivotSwingAtr, pivot.ReactionAtr / MinimumPivotReactionAtr));
                if (best == null || evidence.Score > best.Value.Score)
                    best = evidence;
            }
            foreach (var pivot in esPivots)
            {
                if (pivot.SwingAtr < MinimumPivotSwingAtr ||
                    pivot.ReactionAtr < MinimumPivotReactionAtr ||
                    pivot.UtcMinute.AddMinutes(MinimumLeadCandles) != latestComplete ||
                    HasEquivalentPivot(nqPivots, pivot, false, nqAligned, esInNq, maxDelay, latestComplete))
                    continue;
                var evidence = new LeaderEvidence(
                    pivot,
                    -MinimumLeadCandles,
                    EsName,
                    Math.Min(pivot.SwingAtr / MinimumPivotSwingAtr, pivot.ReactionAtr / MinimumPivotReactionAtr));
                if (best == null || evidence.Score > best.Value.Score)
                    best = evidence;
            }

            if (best == null)
            {
                return StructuralAnalysis.Synchronized(
                    $"Sin estructura grande exclusiva durante {MinimumLeadCandles} velas M1",
                    nqAligned.Length,
                    nqAligned[^1].UtcMinute,
                    esInNq[^1].UtcMinute,
                    ratio,
                    quality,
                    isDivergent);
            }

            var match = best.Value;
            var leaderIsNq = string.Equals(match.LeaderName, NqName, StringComparison.Ordinal);
            var mapping = MapEquivalentPrice(
                match.Pivot.Price,
                match.Pivot.UtcMinute,
                leaderIsNq,
                nqAligned,
                esInNq);

            // The lagger level is computed in NQ points because both series were
            // converted; give it back in the lagger's own quotation as well.
            var expectedNative = leaderIsNq ? mapping.ExpectedPrice / ratio : mapping.ExpectedPrice;

            return new StructuralAnalysis(
                true,
                true,
                $"{match.LeaderName} tiene estructura; el otro mercado aún no",
                match.SignedLag,
                match.Pivot.SwingAtr,
                0,
                match.Pivot.ReactionAtr,
                0,
                nqAligned.Length,
                nqAligned[^1].UtcMinute,
                esInNq[^1].UtcMinute,
                match.Pivot.Kind,
                match.Pivot.UtcMinute,
                latestComplete,
                match.LeaderName,
                mapping.ExpectedPrice,
                expectedNative,
                mapping.Basis,
                ratio,
                quality.Correlation,
                quality.BestLagCandles,
                quality.BestLagCorrelation,
                quality.SpreadPoints,
                quality.SpreadZ,
                quality.SpreadAtr,
                isDivergent);
        }

        // Measures how the two converted series relate right now: contemporaneous
        // correlation of M1 returns, the shift that maximizes that correlation, and
        // how far the current NQ - ES(NQ) spread sits from its own recent behaviour.
        private static SyncQuality MeasureSync(
            StructuralBar[] nqBars,
            StructuralBar[] esInNqBars,
            int window,
            int maximumLag)
        {
            var count = Math.Min(Math.Min(nqBars.Length, esInNqBars.Length), window);
            var offset = nqBars.Length - count;
            var nqReturns = new List<double>(count);
            var esReturns = new List<double>(count);
            for (var index = offset + 1; index < nqBars.Length; index++)
            {
                var nqPrevious = nqBars[index - 1].Close;
                var esPrevious = esInNqBars[index - 1].Close;
                if (nqPrevious <= 0 || esPrevious <= 0)
                    continue;
                nqReturns.Add(Math.Log(nqBars[index].Close / nqPrevious));
                esReturns.Add(Math.Log(esInNqBars[index].Close / esPrevious));
            }

            var correlation = Correlation(nqReturns, esReturns, 0);
            var bestLag = 0;
            var bestLagCorrelation = correlation;
            for (var lag = -maximumLag; lag <= maximumLag; lag++)
            {
                if (lag == 0)
                    continue;
                var candidate = Correlation(nqReturns, esReturns, lag);
                if (candidate > bestLagCorrelation)
                {
                    bestLagCorrelation = candidate;
                    bestLag = lag;
                }
            }

            var spreads = new List<double>(count);
            for (var index = offset; index < nqBars.Length; index++)
                spreads.Add(nqBars[index].Close - esInNqBars[index].Close);

            var spreadNow = spreads.Count == 0 ? 0 : spreads[^1];
            var mean = spreads.Count == 0 ? 0 : spreads.Average();
            var variance = spreads.Count < 2
                ? 0
                : spreads.Sum(x => (x - mean) * (x - mean)) / (spreads.Count - 1);
            var deviation = Math.Sqrt(Math.Max(variance, 0));
            var spreadZ = deviation <= 1e-9 ? 0 : (spreadNow - mean) / deviation;
            var atr = AtrAt(nqBars, nqBars.Length - 1, 14);
            var spreadAtr = atr <= 1e-9 ? 0 : Math.Abs(spreadNow - mean) / atr;

            return new SyncQuality(correlation, bestLag, bestLagCorrelation, spreadNow, spreadZ, spreadAtr);
        }

        // lag > 0 pairs the NQ return at t with the ES return at t + lag, so a positive
        // best lag means ES repeats what NQ already did.
        private static double Correlation(List<double> nqReturns, List<double> esReturns, int lag)
        {
            var left = new List<double>();
            var right = new List<double>();
            for (var index = 0; index < nqReturns.Count; index++)
            {
                var shifted = index + lag;
                if (shifted < 0 || shifted >= esReturns.Count)
                    continue;
                left.Add(nqReturns[index]);
                right.Add(esReturns[shifted]);
            }

            if (left.Count < 8)
                return 0;

            var leftMean = left.Average();
            var rightMean = right.Average();
            var covariance = 0.0;
            var leftVariance = 0.0;
            var rightVariance = 0.0;
            for (var index = 0; index < left.Count; index++)
            {
                var a = left[index] - leftMean;
                var b = right[index] - rightMean;
                covariance += a * b;
                leftVariance += a * a;
                rightVariance += b * b;
            }

            var denominator = Math.Sqrt(leftVariance * rightVariance);
            return denominator <= 1e-12 ? 0 : covariance / denominator;
        }

        private static double Median(List<double> values)
        {
            if (values.Count == 0)
                return 0;
            var sorted = values.ToArray();
            Array.Sort(sorted);
            var middle = sorted.Length / 2;
            return sorted.Length % 2 == 1
                ? sorted[middle]
                : (sorted[middle - 1] + sorted[middle]) / 2.0;
        }

        private static bool HasEquivalentPivot(
            IEnumerable<StructuralPivot> otherPivots,
            StructuralPivot leader,
            bool leaderIsNq,
            StructuralBar[] nqBars,
            StructuralBar[] esInNqBars,
            int maximumDelay,
            DateTime evidenceMinute)
        {
            var earliest = leader.UtcMinute.AddMinutes(-maximumDelay);
            var nqAtLeader = nqBars.First(x => x.UtcMinute == leader.UtcMinute);
            var esAtLeader = esInNqBars.First(x => x.UtcMinute == leader.UtcMinute);
            // Both series are already expressed in NQ points, so what remains between
            // them is an additive residual: preserve the pivot's point distance from the
            // leader close and translate it with the contemporaneous residual.
            var expectedOtherPrice = leaderIsNq
                ? leader.Price + (esAtLeader.Close - nqAtLeader.Close)
                : leader.Price + (nqAtLeader.Close - esAtLeader.Close);
            foreach (var other in otherPivots)
            {
                if (!string.Equals(other.Kind, leader.Kind, StringComparison.Ordinal) ||
                    other.UtcMinute < earliest || other.UtcMinute > evidenceMinute)
                    continue;
                var swingRatio = other.SwingAtr / Math.Max(leader.SwingAtr, 1e-9);
                var reactionRatio = other.ReactionAtr / Math.Max(leader.ReactionAtr, 1e-9);
                var levelDistanceAtr = Math.Abs(other.Price - expectedOtherPrice) / Math.Max(other.Atr, 1e-9);
                if (swingRatio >= 0.60 && swingRatio <= 1.80 &&
                    reactionRatio >= 0.50 && levelDistanceAtr <= 1.50)
                    return true;
            }
            return false;
        }

        private static EquivalentMapping MapEquivalentPrice(
            double leaderPrice,
            DateTime leaderMinute,
            bool leaderIsNq,
            StructuralBar[] nqBars,
            StructuralBar[] esInNqBars)
        {
            var nq = nqBars.First(x => x.UtcMinute == leaderMinute);
            var es = esInNqBars.First(x => x.UtcMinute == leaderMinute);
            var basis = leaderIsNq ? es.Close - nq.Close : nq.Close - es.Close;
            return new EquivalentMapping(leaderPrice + basis, basis);
        }

        private static List<StructuralPivot> DetectPivots(
            StructuralBar[] bars,
            int strength,
            int swingLookback,
            double minimumSwingAtr,
            double minimumReactionAtr)
        {
            var pivots = new List<StructuralPivot>();
            for (var index = Math.Max(strength, swingLookback); index < bars.Length - strength; index++)
            {
                var atr = AtrAt(bars, index, 14);
                if (atr <= 1e-9)
                    continue;

                var current = bars[index];
                var isLow = true;
                var isHigh = true;
                var strictlyLowerLeft = false;
                var strictlyHigherLeft = false;
                for (var offset = 1; offset <= strength; offset++)
                {
                    var left = bars[index - offset];
                    var right = bars[index + offset];
                    isLow &= current.Low <= left.Low && current.Low < right.Low;
                    isHigh &= current.High >= left.High && current.High > right.High;
                    strictlyLowerLeft |= current.Low < left.Low;
                    strictlyHigherLeft |= current.High > left.High;
                }

                var priorHigh = bars.Skip(index - swingLookback).Take(swingLookback).Max(x => x.High);
                var priorLow = bars.Skip(index - swingLookback).Take(swingLookback).Min(x => x.Low);
                var rightHigh = bars.Skip(index + 1).Take(strength).Max(x => x.High);
                var rightLow = bars.Skip(index + 1).Take(strength).Min(x => x.Low);
                if (isLow && strictlyLowerLeft)
                {
                    var swing = (priorHigh - current.Low) / atr;
                    var reaction = (rightHigh - current.Low) / atr;
                    if (swing >= minimumSwingAtr && reaction >= minimumReactionAtr)
                        pivots.Add(new StructuralPivot("INFERIOR", current.UtcMinute, current.Low, atr, swing, reaction));
                }
                if (isHigh && strictlyHigherLeft)
                {
                    var swing = (current.High - priorLow) / atr;
                    var reaction = (current.High - rightLow) / atr;
                    if (swing >= minimumSwingAtr && reaction >= minimumReactionAtr)
                        pivots.Add(new StructuralPivot("SUPERIOR", current.UtcMinute, current.High, atr, swing, reaction));
                }
            }

            return pivots;
        }

        private static double AtrAt(StructuralBar[] bars, int index, int period)
        {
            var first = Math.Max(1, index - period + 1);
            var sum = 0.0;
            var count = 0;
            for (var cursor = first; cursor <= index; cursor++)
            {
                if (bars[cursor].UtcMinute - bars[cursor - 1].UtcMinute != TimeSpan.FromMinutes(1))
                    return 0;
                var current = bars[cursor];
                var previous = bars[cursor - 1];
                sum += Math.Max(
                    current.High - current.Low,
                    Math.Max(Math.Abs(current.High - previous.Close), Math.Abs(current.Low - previous.Close)));
                count++;
            }
            return count == 0 ? 0 : sum / count;
        }

        private static string BuildPivotDetail(string leader, StructuralAnalysis analysis)
            => string.Format(
                CultureInfo.InvariantCulture,
                "{0} formó pivote {1}; tras {2} velas el otro mercado sigue sin estructura equivalente | NY pivote {3}, evidencia {4} | nivel equivalente {5:0.00} NQ ({6:0.00} nativo) | swing {7:0.0} ATR | reacción {8:0.0} ATR | corr {9:0.00} lag {10:+0;-0;0}",
                leader,
                analysis.PivotKind,
                Math.Abs(analysis.LagCandles),
                FormatNy(analysis.LeaderPivotMinute),
                FormatNy(analysis.LaggerPivotMinute),
                analysis.ExpectedLaggerPriceNq,
                analysis.ExpectedLaggerPriceNative,
                analysis.LeaderSwingAtr,
                analysis.LeaderReactionAtr,
                analysis.Correlation,
                analysis.BestLagCandles);

        private static string BuildSyncDetail(StructuralAnalysis analysis)
        {
            var lagText = analysis.BestLagCandles == 0
                ? "sin desfase"
                : analysis.BestLagCandles > 0
                    ? $"NQ adelanta {analysis.BestLagCandles} velas (corr {analysis.BestLagCorrelation:0.00})"
                    : $"ES adelanta {-analysis.BestLagCandles} velas (corr {analysis.BestLagCorrelation:0.00})";
            return string.Format(
                CultureInfo.InvariantCulture,
                "corr M1 {0:0.00} | {1} | spread {2:+0.00;-0.00;0.00} pts NQ (z {3:0.00}, {4:0.00} ATR) | historial común {5}",
                analysis.Correlation,
                lagText,
                analysis.SpreadPoints,
                analysis.SpreadZ,
                analysis.SpreadAtr,
                analysis.ComparedCandles);
        }

        private string BuildTelegramMessage(DateTime now, Report report)
        {
            var header = report.Status == StatusDivergence
                ? "⚠️⚠️ DIVERGENCIA NQ/ES ⚠️⚠️"
                : $"🚨🚨 {report.LeaderName} LIDERA 🚨🚨";
            var burstLine = string.IsNullOrWhiteSpace(report.LiquidityBurstId)
                ? $"Liquidity Burst 1s: no detectado en los últimos {LiquidityBurstMaxAgeSeconds}s"
                : string.Format(
                    CultureInfo.InvariantCulture,
                    "Liquidity Burst 1s: {0} | {1} | NY {2} | px {3:0.00} | Δ1s {4:0} | z {5:0.00} | v {6:0.00}t/s",
                    report.LiquidityBurstSide,
                    report.LiquidityBurstAlignment,
                    FormatNy(report.LiquidityBurstUtc),
                    report.LiquidityBurstPrice,
                    report.LiquidityBurstDelta1s,
                    report.LiquidityBurstZScore,
                    report.LiquidityBurstVelocity1s);
            return string.Join(Environment.NewLine,
                header,
                "ALERTA INFORMATIVA DE DESFASE — decisión y riesgo manuales",
                $"DETECCIÓN REAL | NY {FormatNy(now)}",
                $"LÍDER CONFIRMADO: {(string.IsNullOrWhiteSpace(report.LeaderName) ? "ninguno" : report.LeaderName)}",
                $"ESCENARIO: {report.ExpectedSide} en {report.ExpectedLaggerName}",
                $"PIVOTE DEL LÍDER: NY {FormatNy(report.LeaderPivotMinute)} | evidencia causal: NY {FormatNy(report.LaggerPivotMinute)}",
                $"NIVEL EQUIVALENTE {report.ExpectedLaggerName}: {report.ExpectedLaggerPriceNative:0.00} nativo ({report.ExpectedLaggerPriceNq:0.00} en puntos NQ) | residuo {report.MappingBasis:+0.00;-0.00;0.00}",
                $"ESCALA ES→NQ: x{report.ScaleRatio:0.0000} | spread {report.SpreadPoints:+0.00;-0.00;0.00} pts NQ (z {report.SpreadZ:0.00})",
                $"CORRELACIÓN M1: {report.Correlation:0.00} | mejor desfase {report.BestLagCandles:+0;-0;0} velas (corr {report.BestLagCorrelation:0.00})",
                report.Detail,
                burstLine,
                report.Prices,
                $"Modelo: pivote 2x2, swing ≥ {MinimumPivotSwingAtr:0.0} ATR, reacción ≥ {MinimumPivotReactionAtr:0.0} ATR",
                $"Ventana válida: {MinimumLeadCandles}-{MaximumLeadCandles} velas M1 | historial común: {report.ComparedCandles}",
                $"Salud: NQ {report.NqAgeMs} ms | ES {report.EsAgeMs} ms");
        }

        private void WriteReportCsv(DateTime now, string trigger, Report report)
        {
            try
            {
                Directory.CreateDirectory(OutputFolder);
                var path = Path.Combine(OutputFolder, "nq_es_structural_sync_reports.csv");
                var writeHeader = !File.Exists(path);
                using var writer = new StreamWriter(path, append: true);
                if (writeHeader)
                {
                    writer.WriteLine("utc;trigger;status;leader;expected_lagger;expected_side;pivot_kind;lag_candles;leader_pivot_utc;evidence_utc;expected_lagger_price_nq;expected_lagger_price_native;mapping_basis;scale_ratio;correlation;best_lag_candles;best_lag_correlation;spread_points_nq;spread_z;spread_atr;leader_swing_atr;lagger_swing_atr;leader_reaction_atr;lagger_reaction_atr;liquidity_burst_id;liquidity_burst_side;liquidity_burst_utc;liquidity_burst_price;liquidity_burst_delta_1s;liquidity_burst_zscore;liquidity_burst_velocity_1s;liquidity_burst_alignment;compared_candles;nq_age_ms;es_age_ms;nq_symbol;nq_bid;nq_ask;nq_mid;es_symbol;es_bid;es_ask;es_mid;es_last;nq_last_bar_utc;es_last_bar_utc");
                }

                writer.WriteLine(string.Join(";",
                    now.ToString("O", CultureInfo.InvariantCulture),
                    trigger,
                    report.Status,
                    report.LeaderName,
                    report.ExpectedLaggerName,
                    report.ExpectedSide,
                    report.PivotKind,
                    report.LagCandles.ToString(CultureInfo.InvariantCulture),
                    report.LeaderPivotMinute.ToString("O", CultureInfo.InvariantCulture),
                    report.LaggerPivotMinute.ToString("O", CultureInfo.InvariantCulture),
                    report.ExpectedLaggerPriceNq.ToString("0.0000", CultureInfo.InvariantCulture),
                    report.ExpectedLaggerPriceNative.ToString("0.0000", CultureInfo.InvariantCulture),
                    report.MappingBasis.ToString("0.0000", CultureInfo.InvariantCulture),
                    report.ScaleRatio.ToString("0.000000", CultureInfo.InvariantCulture),
                    report.Correlation.ToString("0.0000", CultureInfo.InvariantCulture),
                    report.BestLagCandles.ToString(CultureInfo.InvariantCulture),
                    report.BestLagCorrelation.ToString("0.0000", CultureInfo.InvariantCulture),
                    report.SpreadPoints.ToString("0.0000", CultureInfo.InvariantCulture),
                    report.SpreadZ.ToString("0.0000", CultureInfo.InvariantCulture),
                    report.SpreadAtr.ToString("0.0000", CultureInfo.InvariantCulture),
                    report.LeaderSwingAtr.ToString("0.0000", CultureInfo.InvariantCulture),
                    report.LaggerSwingAtr.ToString("0.0000", CultureInfo.InvariantCulture),
                    report.LeaderReactionAtr.ToString("0.0000", CultureInfo.InvariantCulture),
                    report.LaggerReactionAtr.ToString("0.0000", CultureInfo.InvariantCulture),
                    report.LiquidityBurstId,
                    report.LiquidityBurstSide,
                    report.LiquidityBurstUtc.ToString("O", CultureInfo.InvariantCulture),
                    report.LiquidityBurstPrice.ToString(CultureInfo.InvariantCulture),
                    report.LiquidityBurstDelta1s.ToString(CultureInfo.InvariantCulture),
                    report.LiquidityBurstZScore.ToString(CultureInfo.InvariantCulture),
                    report.LiquidityBurstVelocity1s.ToString(CultureInfo.InvariantCulture),
                    report.LiquidityBurstAlignment,
                    report.ComparedCandles.ToString(CultureInfo.InvariantCulture),
                    report.NqAgeMs.ToString(CultureInfo.InvariantCulture),
                    report.EsAgeMs.ToString(CultureInfo.InvariantCulture),
                    Instrument,
                    report.NqBid.ToString(CultureInfo.InvariantCulture),
                    report.NqAsk.ToString(CultureInfo.InvariantCulture),
                    report.NqMid.ToString(CultureInfo.InvariantCulture),
                    report.EsSymbol,
                    report.EsBid.ToString(CultureInfo.InvariantCulture),
                    report.EsAsk.ToString(CultureInfo.InvariantCulture),
                    report.EsMid.ToString(CultureInfo.InvariantCulture),
                    report.EsLast.ToString(CultureInfo.InvariantCulture),
                    report.NqLastMinute.ToString("O", CultureInfo.InvariantCulture),
                    report.EsLastMinute.ToString("O", CultureInfo.InvariantCulture)));
            }
            catch (Exception ex)
            {
                lock (_sync)
                    _lastError = "report_csv:" + ex.GetType().Name;
            }
        }

        private static DateTime ToUtc(DateTime value)
        {
            if (value.Kind == DateTimeKind.Utc)
                return value;
            if (value.Kind == DateTimeKind.Local)
                return value.ToUniversalTime();
            return DateTime.SpecifyKind(value, DateTimeKind.Utc);
        }

        private static DateTime FloorMinute(DateTime utc)
        {
            var normalized = utc.Kind == DateTimeKind.Utc ? utc : utc.ToUniversalTime();
            return new DateTime(normalized.Year, normalized.Month, normalized.Day, normalized.Hour, normalized.Minute, 0, DateTimeKind.Utc);
        }

        private static string FormatNy(DateTime utc)
        {
            if (utc == DateTime.MinValue)
                return "?";
            var normalized = utc.Kind == DateTimeKind.Utc ? utc : utc.ToUniversalTime();
            return TimeZoneInfo.ConvertTimeFromUtc(normalized, NewYorkTimeZone)
                .ToString("yyyy-MM-dd HH:mm", CultureInfo.InvariantCulture);
        }

        private static TimeZoneInfo ResolveNewYorkTimeZone()
        {
            try { return TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time"); }
            catch { return TimeZoneInfo.FindSystemTimeZoneById("America/New_York"); }
        }

        private static long AgeMilliseconds(DateTime now, DateTime value)
        {
            if (value == DateTime.MinValue)
                return long.MaxValue;
            return Math.Max(0, (long)(now - value).TotalMilliseconds);
        }

        private static void TrimBars(SortedDictionary<DateTime, StructuralBar> bars, int keep)
        {
            while (bars.Count > keep)
                bars.Remove(bars.First().Key);
        }

        private static string ReadAllTextShared(string path)
        {
            using var stream = new FileStream(
                path,
                FileMode.Open,
                FileAccess.Read,
                FileShare.ReadWrite | FileShare.Delete);
            using var reader = new StreamReader(stream);
            return reader.ReadToEnd();
        }

        private static string[] ReadAllLinesShared(string path)
        {
            var lines = new List<string>();
            using var stream = new FileStream(
                path,
                FileMode.Open,
                FileAccess.Read,
                FileShare.ReadWrite | FileShare.Delete);
            using var reader = new StreamReader(stream);
            while (reader.ReadLine() is { } line)
                lines.Add(line);
            return lines.ToArray();
        }

        private readonly record struct StructuralBar(
            DateTime UtcMinute,
            double Open,
            double High,
            double Low,
            double Close)
        {
            public bool IsValid => Open > 0 && High >= Low && High > 0 && Low > 0 && Close > 0;

            public StructuralBar Update(double price)
                => new(UtcMinute, Open, Math.Max(High, price), Math.Min(Low, price), price);
        }

        private readonly record struct StructuralPivot(
            string Kind,
            DateTime UtcMinute,
            double Price,
            double Atr,
            double SwingAtr,
            double ReactionAtr);

        private readonly record struct EquivalentMapping(double ExpectedPrice, double Basis);

        private readonly record struct LeaderEvidence(
            StructuralPivot Pivot,
            int SignedLag,
            string LeaderName,
            double Score);

        private readonly record struct SyncQuality(
            double Correlation,
            int BestLagCandles,
            double BestLagCorrelation,
            double SpreadPoints,
            double SpreadZ,
            double SpreadAtr);

        private readonly record struct StructuralAnalysis(
            bool Available,
            bool Confirmed,
            string Reason,
            int LagCandles,
            double LeaderSwingAtr,
            double LaggerSwingAtr,
            double LeaderReactionAtr,
            double LaggerReactionAtr,
            int ComparedCandles,
            DateTime NqLastMinute,
            DateTime EsLastMinute,
            string PivotKind,
            DateTime LeaderPivotMinute,
            DateTime LaggerPivotMinute,
            string LeaderName,
            double ExpectedLaggerPriceNq,
            double ExpectedLaggerPriceNative,
            double MappingBasis,
            double ScaleRatio,
            double Correlation,
            int BestLagCandles,
            double BestLagCorrelation,
            double SpreadPoints,
            double SpreadZ,
            double SpreadAtr,
            bool IsDivergent)
        {
            public static StructuralAnalysis Unavailable(string reason)
                => new(false, false, reason, 0, 0, 0, 0, 0, 0, DateTime.MinValue, DateTime.MinValue, "", DateTime.MinValue, DateTime.MinValue, "", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, false);

            public static StructuralAnalysis Synchronized(
                string reason,
                int comparedCandles,
                DateTime nqLastMinute,
                DateTime esLastMinute,
                double scaleRatio,
                SyncQuality quality,
                bool isDivergent)
                => new(true, false, reason, 0, 0, 0, 0, 0, comparedCandles, nqLastMinute, esLastMinute, "", DateTime.MinValue, DateTime.MinValue, "", 0, 0, 0,
                    scaleRatio,
                    quality.Correlation,
                    quality.BestLagCandles,
                    quality.BestLagCorrelation,
                    quality.SpreadPoints,
                    quality.SpreadZ,
                    quality.SpreadAtr,
                    isDivergent);
        }

        private readonly record struct Report(
            string Status,
            string Detail,
            string Prices,
            Color Color,
            int LagCandles,
            double LeaderSwingAtr,
            double LaggerSwingAtr,
            double LeaderReactionAtr,
            double LaggerReactionAtr,
            int ComparedCandles,
            long NqAgeMs,
            long EsAgeMs,
            decimal NqBid,
            decimal NqAsk,
            decimal NqMid,
            string EsSymbol,
            decimal EsBid,
            decimal EsAsk,
            decimal EsMid,
            decimal EsLast,
            long EsTickTimeMsc,
            double ScaleRatio,
            DateTime NqLastMinute,
            DateTime EsLastMinute,
            string PivotKind,
            DateTime LeaderPivotMinute,
            DateTime LaggerPivotMinute,
            string LeaderName,
            string ExpectedLaggerName,
            string ExpectedSide,
            double ExpectedLaggerPriceNq,
            double ExpectedLaggerPriceNative,
            double MappingBasis,
            double Correlation,
            int BestLagCandles,
            double BestLagCorrelation,
            double SpreadPoints,
            double SpreadZ,
            double SpreadAtr,
            string LiquidityBurstId,
            string LiquidityBurstSide,
            DateTime LiquidityBurstUtc,
            decimal LiquidityBurstPrice,
            decimal LiquidityBurstDelta1s,
            decimal LiquidityBurstZScore,
            decimal LiquidityBurstVelocity1s,
            string LiquidityBurstAlignment);
    }
}
