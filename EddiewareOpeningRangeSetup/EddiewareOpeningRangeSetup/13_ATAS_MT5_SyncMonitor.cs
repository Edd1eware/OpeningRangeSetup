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
    [DisplayName("ATAS L2 vs MT5 Structural Sync")]
    public class AtasMt5SyncMonitor : Indicator
    {
        private const string BridgeVersion = "ATAS_MT5_SYNC_V1";
        private const string HistoryVersion = "ATAS_MT5_HISTORY_V1";
        private const string TelegramSeries = "atas_mt5_structural_sync";

        private readonly object _sync = new();
        private readonly SortedDictionary<decimal, decimal> _bids = new();
        private readonly SortedDictionary<decimal, decimal> _asks = new();
        private readonly SortedDictionary<DateTime, StructuralBar> _atasBars = new();
        private readonly SortedDictionary<DateTime, StructuralBar> _mt5Bars = new();
        private readonly RenderFont _titleFont = new("Arial", 11);
        private readonly RenderFont _detailFont = new("Arial", 9);

        private TimeSpan _timerPeriod;
        private bool _timerSubscribed;
        private int _monitorTickRunning;
        private DateTime _lastAtasArrivalUtc;
        private DateTime _lastMt5BridgeUtc;
        private DateTime _lastMt5HistoryUtc;
        private DateTime _lastHistoryReadAttemptUtc;
        private DateTime _lastStructuralCheckUtc;
        private DisplayAwakeGuard? _displayAwakeGuard;
        private decimal _bestBid;
        private decimal _bestAsk;
        private decimal _atasMid;
        private decimal _lastAtasTrade;
        private decimal _mt5Bid;
        private decimal _mt5Ask;
        private decimal _mt5Mid;
        private decimal _mt5Last;
        private long _mt5Sequence = -1;
        private long _mt5TickTimeMsc;
        private string _mt5Symbol = "";
        private string _activeLeadState = "";
        private string _lastAlertSignature = "";
        private string _displayStatus = "INICIANDO";
        private string _displayDetail = "Esperando velas M1 y libro L2";
        private string _displayPrices = "";
        private Color _displayColor = Color.Gold;
        private string _lastError = "";

        [Display(Name = "Archivo precio MT5", Order = 1, GroupName = "Conexión")]
        public string Mt5BridgeFile { get; set; } =
            @"C:\Users\k_99_\AppData\Roaming\MetaQuotes\Terminal\Common\Files\ATAS_MT5_Sync\mt5_price.csv";

        [Display(Name = "Historial M1 MT5", Order = 2, GroupName = "Conexión")]
        public string Mt5HistoryFile { get; set; } =
            @"C:\Users\k_99_\AppData\Roaming\MetaQuotes\Terminal\Common\Files\ATAS_MT5_Sync\mt5_m1_history.csv";

        [Display(Name = "Carpeta Telegram", Order = 3, GroupName = "Conexión")]
        public string TelegramFolder { get; set; } =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score";

        [Display(Name = "Carpeta de diagnóstico", Order = 4, GroupName = "Conexión")]
        public string OutputFolder { get; set; } =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\atas_mt5_sync";

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

        [Range(0.0, 1.0)]
        [Display(Name = "Correlación estructural mínima", Order = 15, GroupName = "Estructura M1")]
        public double MinimumStructuralCorrelation { get; set; } = 0.55;

        [Range(0.0, 1.0)]
        [Display(Name = "Coincidencia direccional mínima", Order = 16, GroupName = "Estructura M1")]
        public double MinimumDirectionAgreement { get; set; } = 0.65;

        [Range(0.0, 0.5)]
        [Display(Name = "Ventaja sobre desfase cero", Order = 17, GroupName = "Estructura M1")]
        public double MinimumCorrelationEdge { get; set; } = 0.08;

        [Range(1, 30)]
        [Display(Name = "Datos vencidos después de (s)", Order = 18, GroupName = "Estructura M1")]
        public int StaleAfterSeconds { get; set; } = 3;

        [Range(50, 1000)]
        [Display(Name = "Lectura del puente (ms)", Order = 19, GroupName = "Estructura M1")]
        public int SampleIntervalMilliseconds { get; set; } = 100;

        public AtasMt5SyncMonitor()
        {
            Name = "ATAS L2 vs MT5 Structural Sync";
            DenyToChangePanel = true;
            EnableCustomDrawing = true;
            SubscribeToDrawingEvents(DrawingLayouts.LatestBar);
        }

        protected override void OnInitialize()
        {
            base.OnInitialize();

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
                    _atasBars[minute] = structuralBar;
                    TrimBars(_atasBars, 360);
                }
            }
            catch (Exception ex)
            {
                lock (_sync)
                    _lastError = "atas_candle:" + ex.GetType().Name;
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
                _lastAtasTrade = trade.Price;
        }

        protected override void OnRender(RenderContext context, DrawingLayouts layout)
        {
            if (Container == null)
                return;

            var region = Container.Region;
            string status;
            string detail;
            string prices;
            Color color;

            lock (_sync)
            {
                status = _displayStatus;
                detail = _displayDetail;
                prices = _displayPrices;
                color = _displayColor;
            }

            var x = region.Left + 10;
            var y = region.Top + 10;
            context.DrawString("ATAS L2 vs CFD MT5 | " + status, _titleFont, color, x, y);
            context.DrawString(detail, _detailFont, Color.White, x, y + 19);
            context.DrawString(prices, _detailFont, Color.LightGray, x, y + 35);
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
                    _atasMid = (_bestBid + _bestAsk) / 2m;
                    UpdateLiveAtasBar(arrivalUtc, (double)_atasMid);
                }

                _lastAtasArrivalUtc = arrivalUtc;
            }
        }

        private void UpdateLiveAtasBar(DateTime utc, double price)
        {
            var minute = FloorMinute(utc);
            if (_atasBars.TryGetValue(minute, out var current))
                _atasBars[minute] = current.Update(price);
            else
                _atasBars[minute] = new StructuralBar(minute, price, price, price, price);
        }

        private void MonitorTick()
        {
            if (System.Threading.Interlocked.Exchange(ref _monitorTickRunning, 1) != 0)
                return;

            try
            {
                var now = DateTime.UtcNow;
                ReadMt5Bridge();
                if (now - _lastHistoryReadAttemptUtc >= TimeSpan.FromSeconds(2))
                {
                    _lastHistoryReadAttemptUtc = now;
                    ReadMt5History();
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

        private void ReadMt5Bridge()
        {
            try
            {
                if (!File.Exists(Mt5BridgeFile))
                    return;

                var fields = ReadAllTextShared(Mt5BridgeFile).Trim().Split(';');
                if (fields.Length < 8 || !string.Equals(fields[0], BridgeVersion, StringComparison.Ordinal))
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
                    if (sequence == _mt5Sequence)
                        return;

                    _mt5Sequence = sequence;
                    _mt5Symbol = fields[1];
                    _mt5Bid = bid;
                    _mt5Ask = ask;
                    _mt5Last = last;
                    _mt5Mid = bid > 0 && ask > 0 ? (bid + ask) / 2m : last;
                    _mt5TickTimeMsc = tickTimeMsc;
                    _lastMt5BridgeUtc = File.GetLastWriteTimeUtc(Mt5BridgeFile);
                    _lastError = "";
                }
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException)
            {
                lock (_sync)
                    _lastError = "mt5_bridge:access_denied";
            }
            catch (Exception ex)
            {
                lock (_sync)
                    _lastError = "mt5_bridge:" + ex.GetType().Name;
            }
        }

        private void ReadMt5History()
        {
            try
            {
                if (!File.Exists(Mt5HistoryFile))
                    return;

                var lines = ReadAllLinesShared(Mt5HistoryFile);
                if (lines.Length < 3)
                    return;

                var header = lines[0].Split(';');
                if (header.Length < 2 || !string.Equals(header[0], HistoryVersion, StringComparison.Ordinal))
                    return;

                var parsed = new SortedDictionary<DateTime, StructuralBar>();
                for (var index = 1; index < lines.Length; index++)
                {
                    var fields = lines[index].Split(';');
                    if (fields.Length < 6 ||
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
                    _mt5Bars.Clear();
                    foreach (var item in parsed)
                        _mt5Bars[item.Key] = item.Value;
                    TrimBars(_mt5Bars, 360);
                    _mt5Symbol = header[1];
                    _lastMt5HistoryUtc = File.GetLastWriteTimeUtc(Mt5HistoryFile);
                }
            }
            catch (IOException) { }
            catch (Exception ex)
            {
                lock (_sync)
                    _lastError = "mt5_history:" + ex.GetType().Name;
            }
        }

        private void UpdateLiveDisplay(DateTime now)
        {
            var atasAge = AgeMilliseconds(now, _lastAtasArrivalUtc);
            var mt5Age = AgeMilliseconds(now, _lastMt5BridgeUtc);
            var staleMs = Math.Max(1, StaleAfterSeconds) * 1000L;

            if (_atasMid <= 0 || atasAge > staleMs)
            {
                _displayStatus = "SIN DATOS L2 ATAS";
                _displayColor = Color.OrangeRed;
            }
            else if (_mt5Mid <= 0 || mt5Age > staleMs)
            {
                _displayStatus = "SIN DATOS CFD MT5";
                _displayColor = Color.OrangeRed;
            }
            else if (_atasBars.Count < MinimumCompletedCandles || _mt5Bars.Count < MinimumCompletedCandles)
            {
                _displayStatus = "CARGANDO ESTRUCTURA M1";
                _displayColor = Color.Gold;
            }

            _displayDetail = $"M1 ATAS={_atasBars.Count} MT5={_mt5Bars.Count} | edad L2={atasAge} ms CFD={mt5Age} ms";
            if (!string.IsNullOrWhiteSpace(_lastError))
                _displayDetail += " | " + _lastError;
            _displayPrices = string.Format(
                CultureInfo.InvariantCulture,
                "ATAS {0}: {1:0.00}/{2:0.00} | CFD {3}: {4:0.00}/{5:0.00} | escala {6:0.0000}",
                Instrument,
                _bestBid,
                _bestAsk,
                string.IsNullOrWhiteSpace(_mt5Symbol) ? "?" : _mt5Symbol,
                _mt5Bid,
                _mt5Ask,
                _mt5Mid > 0 ? _atasMid / _mt5Mid : 0);
        }

        private void CheckImmediateAlert(DateTime now)
        {
            Report report;
            lock (_sync)
                report = BuildReport(now);

            var isLead = report.Status == "L2 ATAS LIDERA" || report.Status == "CFD MT5 LIDERA";
            var shouldAlert = false;
            var signature = $"{report.Status}|{report.LagCandles}|{report.AtasLastMinute:O}|{report.Mt5LastMinute:O}";
            lock (_sync)
            {
                _displayStatus = report.Status;
                _displayDetail = report.Detail;
                _displayPrices = report.Prices;
                _displayColor = report.Color;

                if (!isLead)
                {
                    _activeLeadState = "";
                }
                else if (!string.Equals(_activeLeadState, report.Status, StringComparison.Ordinal) &&
                         !string.Equals(_lastAlertSignature, signature, StringComparison.Ordinal))
                {
                    _activeLeadState = report.Status;
                    _lastAlertSignature = signature;
                    shouldAlert = true;
                }
            }

            if (shouldAlert)
                ProduceAlert(now, report);
        }

        private void ProduceAlert(DateTime now, Report report)
        {
            WriteReportCsv(now, "alerta", report);
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
                    screenshot);
                return;
            }

            lock (_sync)
                _lastError = "screenshot_failed";
            TelegramTradeNotifier.QueuePeriodicStatus(
                TelegramFolder,
                TelegramSeries + "_alert_fallback",
                FloorMinute(now),
                caption + Environment.NewLine + "Captura no disponible");
        }

        private Report BuildReport(DateTime now)
        {
            var atasAge = AgeMilliseconds(now, _lastAtasArrivalUtc);
            var mt5Age = AgeMilliseconds(now, _lastMt5BridgeUtc);
            var staleMs = Math.Max(1, StaleAfterSeconds) * 1000L;
            var analysis = AnalyzeStructure(now);
            var status = "EN SINCRONÍA";
            var detail = "Sin desplazamiento estructural confirmado de 3 velas o más";
            var color = Color.LimeGreen;

            if (_atasMid <= 0 || atasAge > staleMs)
            {
                status = "SIN DATOS L2 ATAS";
                detail = $"Última llegada L2 hace {atasAge} ms";
                color = Color.OrangeRed;
            }
            else if (_mt5Mid <= 0 || mt5Age > staleMs)
            {
                status = "SIN DATOS CFD MT5";
                detail = $"Puente CFD hace {mt5Age} ms";
                color = Color.OrangeRed;
            }
            else if (!analysis.Available)
            {
                status = "CARGANDO ESTRUCTURA M1";
                detail = analysis.Reason;
                color = Color.Gold;
            }
            else if (analysis.Confirmed && analysis.LagCandles >= MinimumLeadCandles)
            {
                status = "L2 ATAS LIDERA";
                detail = $"ATAS adelanta {analysis.LagCandles} velas M1 | corr={analysis.Correlation:0.00} dir={analysis.DirectionAgreement:P0}";
                color = Color.DeepSkyBlue;
            }
            else if (analysis.Confirmed && analysis.LagCandles <= -MinimumLeadCandles)
            {
                status = "CFD MT5 LIDERA";
                detail = $"CFD adelanta {Math.Abs(analysis.LagCandles)} velas M1 | corr={analysis.Correlation:0.00} dir={analysis.DirectionAgreement:P0}";
                color = Color.Violet;
            }
            else
            {
                detail = $"desfase estructural {analysis.LagCandles:+0;-0;0} velas | corr={analysis.Correlation:0.00} dir={analysis.DirectionAgreement:P0}";
            }

            var scaleRatio = _mt5Mid > 0 ? _atasMid / _mt5Mid : 0;
            var prices = string.Format(
                CultureInfo.InvariantCulture,
                "ATAS {0} L2 {1:0.00}/{2:0.00} | CFD {3} {4:0.00}/{5:0.00} | escala {6:0.0000}",
                Instrument,
                _bestBid,
                _bestAsk,
                string.IsNullOrWhiteSpace(_mt5Symbol) ? "?" : _mt5Symbol,
                _mt5Bid,
                _mt5Ask,
                scaleRatio);

            return new Report(
                status,
                detail,
                prices,
                color,
                analysis.LagCandles,
                analysis.Correlation,
                analysis.DirectionAgreement,
                analysis.ZeroLagCorrelation,
                analysis.ComparedCandles,
                atasAge,
                mt5Age,
                _bestBid,
                _bestAsk,
                _atasMid,
                _mt5Symbol,
                _mt5Bid,
                _mt5Ask,
                _mt5Mid,
                _mt5Last,
                _mt5TickTimeMsc,
                scaleRatio,
                analysis.AtasLastMinute,
                analysis.Mt5LastMinute);
        }

        private StructuralAnalysis AnalyzeStructure(DateTime now)
        {
            var currentMinute = FloorMinute(now);
            var take = Math.Clamp(StructuralWindowCandles, 20, 240) + Math.Clamp(MaximumLeadCandles, 3, 20) + 20;
            var atas = _atasBars.Values.Where(x => x.UtcMinute < currentMinute).TakeLast(take).ToArray();
            var mt5 = _mt5Bars.Values.Where(x => x.UtcMinute < currentMinute).TakeLast(take).ToArray();
            var minimum = Math.Clamp(MinimumCompletedCandles, 12, 120);

            if (atas.Length < minimum || mt5.Length < minimum)
            {
                return StructuralAnalysis.Unavailable(
                    $"Velas completas ATAS={atas.Length}, MT5={mt5.Length}; mínimo={minimum}");
            }

            var requestedWindow = Math.Clamp(StructuralWindowCandles, 20, 240);
            var commonCount = Math.Min(Math.Min(atas.Length, mt5.Length), requestedWindow + MaximumLeadCandles + 15);
            atas = atas.TakeLast(commonCount).ToArray();
            mt5 = mt5.TakeLast(commonCount).ToArray();
            var featureA = BuildStructuralFeatures(atas);
            var featureM = BuildStructuralFeatures(mt5);
            var maxLag = Math.Clamp(MaximumLeadCandles, Math.Clamp(MinimumLeadCandles, 3, 10), 20);
            var bestScore = double.NegativeInfinity;
            var bestCorrelation = -1.0;
            var bestAgreement = 0.0;
            var bestLag = 0;
            var bestCount = 0;
            var zeroLagCorrelation = 0.0;

            for (var lag = -maxLag; lag <= maxLag; lag++)
            {
                var match = Correlate(featureA, featureM, lag);
                if (!match.Available)
                    continue;

                if (lag == 0)
                    zeroLagCorrelation = match.Correlation;

                var score = match.Correlation * (0.70 + 0.30 * match.DirectionAgreement);
                if (score > bestScore)
                {
                    bestScore = score;
                    bestCorrelation = match.Correlation;
                    bestAgreement = match.DirectionAgreement;
                    bestLag = lag;
                    bestCount = match.Count;
                }
            }

            if (double.IsNegativeInfinity(bestScore))
                return StructuralAnalysis.Unavailable("No hubo variación estructural suficiente");

            var minLag = Math.Clamp(MinimumLeadCandles, 3, 10);
            var confirmed = Math.Abs(bestLag) >= minLag &&
                            bestCorrelation >= MinimumStructuralCorrelation &&
                            bestAgreement >= MinimumDirectionAgreement &&
                            bestCorrelation - zeroLagCorrelation >= MinimumCorrelationEdge;

            return new StructuralAnalysis(
                true,
                confirmed,
                "",
                bestLag,
                bestCorrelation,
                bestAgreement,
                zeroLagCorrelation,
                bestCount,
                atas[^1].UtcMinute,
                mt5[^1].UtcMinute);
        }

        private static double[] BuildStructuralFeatures(StructuralBar[] bars)
        {
            var features = new double[bars.Length];
            for (var index = 1; index < bars.Length; index++)
            {
                var previous = bars[index - 1];
                var current = bars[index];
                var atrStart = Math.Max(0, index - 14);
                var rangeSum = 0.0;
                var rangeCount = 0;
                for (var rangeIndex = atrStart; rangeIndex < index; rangeIndex++)
                {
                    var range = bars[rangeIndex].High - bars[rangeIndex].Low;
                    if (range > 0)
                    {
                        rangeSum += range;
                        rangeCount++;
                    }
                }

                var atr = rangeCount == 0 ? Math.Max(current.High - current.Low, previous.Close * 1e-6) : rangeSum / rangeCount;
                atr = Math.Max(atr, previous.Close * 1e-7);
                var normalizedReturn = Clamp((current.Close - previous.Close) / atr, -3.0, 3.0);
                var candleRange = Math.Max(current.High - current.Low, atr * 0.10);
                var normalizedBody = Clamp((current.Close - current.Open) / candleRange, -1.0, 1.0);
                var breakout = current.Close > previous.High ? 1.0 : current.Close < previous.Low ? -1.0 : 0.0;
                features[index] = 0.65 * normalizedReturn + 0.25 * normalizedBody + 0.10 * breakout;
            }

            return features;
        }

        private static StructuralMatch Correlate(double[] atas, double[] mt5, int lag)
        {
            double sumA = 0, sumM = 0, sumAA = 0, sumMM = 0, sumAM = 0;
            var count = 0;
            var directional = 0;
            var directionalMatches = 0;

            for (var index = 1; index < atas.Length; index++)
            {
                var mt5Index = index + lag;
                if (mt5Index < 1 || mt5Index >= mt5.Length)
                    continue;

                var a = atas[index];
                var m = mt5[mt5Index];
                sumA += a;
                sumM += m;
                sumAA += a * a;
                sumMM += m * m;
                sumAM += a * m;
                count++;

                if (Math.Abs(a) >= 0.15 && Math.Abs(m) >= 0.15)
                {
                    directional++;
                    if (Math.Sign(a) == Math.Sign(m))
                        directionalMatches++;
                }
            }

            if (count < 12)
                return StructuralMatch.Unavailable;

            var covariance = count * sumAM - sumA * sumM;
            var varianceA = count * sumAA - sumA * sumA;
            var varianceM = count * sumMM - sumM * sumM;
            var denominator = Math.Sqrt(Math.Max(0, varianceA) * Math.Max(0, varianceM));
            if (denominator <= 1e-12)
                return StructuralMatch.Unavailable;

            var correlation = covariance / denominator;
            var agreement = directional == 0 ? 0.0 : (double)directionalMatches / directional;
            return new StructuralMatch(true, correlation, agreement, count);
        }

        private string BuildTelegramMessage(DateTime now, Report report)
        {
            return string.Join(Environment.NewLine,
                $"ALERTA DESFASE ATAS vs CFD | {now.ToLocalTime():yyyy-MM-dd HH:mm:ss}",
                $"ESTADO: {report.Status}",
                report.Detail,
                report.Prices,
                $"Modelo: estructura M1 normalizada por ATR | mínimo {MinimumLeadCandles} velas",
                $"Velas comparadas: {report.ComparedCandles} | corr0={report.ZeroLagCorrelation:0.00}",
                $"Salud: L2 {report.AtasAgeMs} ms | CFD {report.Mt5AgeMs} ms");
        }

        private void WriteReportCsv(DateTime now, string trigger, Report report)
        {
            try
            {
                Directory.CreateDirectory(OutputFolder);
                var path = Path.Combine(OutputFolder, "atas_mt5_structural_sync_reports.csv");
                var writeHeader = !File.Exists(path);
                using var writer = new StreamWriter(path, append: true);
                if (writeHeader)
                {
                    writer.WriteLine("utc;trigger;status;lag_candles;correlation;direction_agreement;zero_lag_correlation;compared_candles;atas_age_ms;mt5_age_ms;atas_symbol;atas_bid;atas_ask;atas_mid;mt5_symbol;mt5_bid;mt5_ask;mt5_mid;mt5_last;scale_ratio;atas_last_bar_utc;mt5_last_bar_utc");
                }

                writer.WriteLine(string.Join(";",
                    now.ToString("O", CultureInfo.InvariantCulture),
                    trigger,
                    report.Status,
                    report.LagCandles.ToString(CultureInfo.InvariantCulture),
                    report.Correlation.ToString("0.0000", CultureInfo.InvariantCulture),
                    report.DirectionAgreement.ToString("0.0000", CultureInfo.InvariantCulture),
                    report.ZeroLagCorrelation.ToString("0.0000", CultureInfo.InvariantCulture),
                    report.ComparedCandles.ToString(CultureInfo.InvariantCulture),
                    report.AtasAgeMs.ToString(CultureInfo.InvariantCulture),
                    report.Mt5AgeMs.ToString(CultureInfo.InvariantCulture),
                    Instrument,
                    report.AtasBid.ToString(CultureInfo.InvariantCulture),
                    report.AtasAsk.ToString(CultureInfo.InvariantCulture),
                    report.AtasMid.ToString(CultureInfo.InvariantCulture),
                    report.Mt5Symbol,
                    report.Mt5Bid.ToString(CultureInfo.InvariantCulture),
                    report.Mt5Ask.ToString(CultureInfo.InvariantCulture),
                    report.Mt5Mid.ToString(CultureInfo.InvariantCulture),
                    report.Mt5Last.ToString(CultureInfo.InvariantCulture),
                    report.ScaleRatio.ToString(CultureInfo.InvariantCulture),
                    report.AtasLastMinute.ToString("O", CultureInfo.InvariantCulture),
                    report.Mt5LastMinute.ToString("O", CultureInfo.InvariantCulture)));
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

        private static long AgeMilliseconds(DateTime now, DateTime value)
        {
            if (value == DateTime.MinValue)
                return long.MaxValue;
            return Math.Max(0, (long)(now - value).TotalMilliseconds);
        }

        private static double Clamp(double value, double minimum, double maximum)
            => Math.Max(minimum, Math.Min(maximum, value));

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

        private readonly record struct StructuralMatch(
            bool Available,
            double Correlation,
            double DirectionAgreement,
            int Count)
        {
            public static StructuralMatch Unavailable => new(false, 0, 0, 0);
        }

        private readonly record struct StructuralAnalysis(
            bool Available,
            bool Confirmed,
            string Reason,
            int LagCandles,
            double Correlation,
            double DirectionAgreement,
            double ZeroLagCorrelation,
            int ComparedCandles,
            DateTime AtasLastMinute,
            DateTime Mt5LastMinute)
        {
            public static StructuralAnalysis Unavailable(string reason)
                => new(false, false, reason, 0, 0, 0, 0, 0, DateTime.MinValue, DateTime.MinValue);
        }

        private readonly record struct Report(
            string Status,
            string Detail,
            string Prices,
            Color Color,
            int LagCandles,
            double Correlation,
            double DirectionAgreement,
            double ZeroLagCorrelation,
            int ComparedCandles,
            long AtasAgeMs,
            long Mt5AgeMs,
            decimal AtasBid,
            decimal AtasAsk,
            decimal AtasMid,
            string Mt5Symbol,
            decimal Mt5Bid,
            decimal Mt5Ask,
            decimal Mt5Mid,
            decimal Mt5Last,
            long Mt5TickTimeMsc,
            decimal ScaleRatio,
            DateTime AtasLastMinute,
            DateTime Mt5LastMinute);
    }
}
