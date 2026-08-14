using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Linq;
using ATAS.DataFeedsCore;

namespace ATAS.Indicators
{
    // Publishes the live L1 quote and the rolling M1 structure of the chart it is
    // attached to, so another ATAS chart can compare against it.
    //
    // ATAS indicators can only observe the instrument of their own chart:
    // IOnlineDataProvider is bound to that instrument and exposes no cross-symbol
    // request. A file bridge inside the same platform is therefore the only causal
    // way to put ES and NQ side by side, and it reuses the schema shape the MT5
    // bridge already used.
    //
    // Attach this to an ES M1 chart. The NQ chart runs NqEsStructuralSyncMonitor,
    // which reads these two files.
    [DisplayName("ES M1 Feed Publisher")]
    public class EsFeedPublisher : Indicator
    {
        public const string PriceVersion = "ATAS_ES_SYNC_V1";
        public const string HistoryVersion = "ATAS_ES_HISTORY_V1";
        public const string DefaultFolder =
            @"C:\Users\k_99_\Desktop\codding\data_footprint_generator\trade_results_score\atas_es_sync";
        public const string DefaultPriceFile = "es_price.csv";
        public const string DefaultHistoryFile = "es_m1_history.csv";

        private const int HistoryBars = 360;

        private readonly object _sync = new();
        private readonly SortedDictionary<decimal, decimal> _bids = new();
        private readonly SortedDictionary<decimal, decimal> _asks = new();
        private readonly SortedDictionary<DateTime, PublishedBar> _bars = new();

        private TimeSpan _timerPeriod;
        private bool _timerSubscribed;
        private int _publishRunning;
        private decimal _bestBid;
        private decimal _bestAsk;
        private decimal _lastTrade;
        private long _sequence;
        private long _publishedSequence = -1;
        private DateTime _lastHistoryWriteUtc;
        private string _lastError = "";

        public EsFeedPublisher()
            : base(true)
        {
            Name = "ES M1 Feed Publisher";
            DenyToChangePanel = true;
            DataSeries[0].IsHidden = true;
            EnableCustomDrawing = false;
        }

        [Display(Name = "Carpeta del puente", Order = 1, GroupName = "Publicación")]
        public string OutputFolder { get; set; } = DefaultFolder;

        [Display(Name = "Archivo de precio", Order = 2, GroupName = "Publicación")]
        public string PriceFileName { get; set; } = DefaultPriceFile;

        [Display(Name = "Archivo de historial M1", Order = 3, GroupName = "Publicación")]
        public string HistoryFileName { get; set; } = DefaultHistoryFile;

        [Range(50, 1000)]
        [Display(Name = "Intervalo de publicación (ms)", Order = 4, GroupName = "Publicación")]
        public int PublishIntervalMilliseconds { get; set; } = 100;

        [Range(1, 30)]
        [Display(Name = "Intervalo de historial (s)", Order = 5, GroupName = "Publicación")]
        public int HistoryIntervalSeconds { get; set; } = 2;

        protected override void OnInitialize()
        {
            base.OnInitialize();
            SeedMarketDepth();
            _timerPeriod = TimeSpan.FromMilliseconds(Math.Clamp(PublishIntervalMilliseconds, 50, 1000));
            SubscribeToTimer(_timerPeriod, PublishTick);
            _timerSubscribed = true;
        }

        protected override void OnDispose()
        {
            if (_timerSubscribed)
            {
                try { UnsubscribeFromTimer(_timerPeriod, PublishTick); }
                catch { }
                _timerSubscribed = false;
            }

            base.OnDispose();
        }

        protected override void OnCalculate(int bar, decimal value)
        {
            try
            {
                var candle = GetCandle(bar);
                if (candle == null)
                    return;

                var minute = FloorMinute(ToUtc(candle.Time));
                var published = new PublishedBar(
                    minute,
                    (double)candle.Open,
                    (double)candle.High,
                    (double)candle.Low,
                    (double)candle.Close,
                    (double)candle.Volume);

                if (!published.IsValid)
                    return;

                lock (_sync)
                {
                    _bars[minute] = published;
                    while (_bars.Count > HistoryBars)
                        _bars.Remove(_bars.First().Key);
                }
            }
            catch (Exception ex)
            {
                lock (_sync)
                    _lastError = "candle:" + ex.GetType().Name;
            }
        }

        protected override void MarketDepthChanged(MarketDataArg depth)
        {
            base.MarketDepthChanged(depth);
            ApplyDepth(depth);
        }

        protected override void MarketDepthsChanged(IEnumerable<MarketDataArg> depths)
        {
            base.MarketDepthsChanged(depths);
            if (depths == null)
                return;

            foreach (var depth in depths)
                ApplyDepth(depth);
        }

        protected override void OnNewTrade(MarketDataArg trade)
        {
            base.OnNewTrade(trade);
            if (trade == null)
                return;

            lock (_sync)
            {
                _lastTrade = trade.Price;
                _sequence++;
            }
        }

        private void SeedMarketDepth()
        {
            try
            {
                foreach (var depth in GetMarketDepthSnapshot())
                    ApplyDepth(depth);
            }
            catch (Exception ex)
            {
                lock (_sync)
                    _lastError = "depth_snapshot:" + ex.GetType().Name;
            }
        }

        private void ApplyDepth(MarketDataArg? depth)
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
                _sequence++;
            }
        }

        private void PublishTick()
        {
            if (System.Threading.Interlocked.Exchange(ref _publishRunning, 1) != 0)
                return;

            try
            {
                var now = DateTime.UtcNow;
                WritePriceFile(now);
                if (now - _lastHistoryWriteUtc >= TimeSpan.FromSeconds(Math.Clamp(HistoryIntervalSeconds, 1, 30)))
                {
                    _lastHistoryWriteUtc = now;
                    WriteHistoryFile();
                }
            }
            catch (Exception ex)
            {
                lock (_sync)
                    _lastError = "publish:" + ex.GetType().Name;
            }
            finally
            {
                System.Threading.Volatile.Write(ref _publishRunning, 0);
            }
        }

        private void WritePriceFile(DateTime now)
        {
            decimal bid;
            decimal ask;
            decimal last;
            long sequence;

            lock (_sync)
            {
                // Nothing moved since the last publication: leaving the file untouched
                // is what lets the monitor detect a dead feed through its timestamp.
                if (_sequence == _publishedSequence)
                    return;

                bid = _bestBid;
                ask = _bestAsk;
                last = _lastTrade;
                sequence = _sequence;
                _publishedSequence = sequence;
            }

            if (bid <= 0 && ask <= 0 && last <= 0)
                return;

            var mid = bid > 0 && ask > 0 && bid <= ask ? (bid + ask) / 2m : last;
            var line = string.Join(";",
                PriceVersion,
                Instrument,
                bid.ToString(CultureInfo.InvariantCulture),
                ask.ToString(CultureInfo.InvariantCulture),
                last.ToString(CultureInfo.InvariantCulture),
                new DateTimeOffset(now).ToUnixTimeMilliseconds().ToString(CultureInfo.InvariantCulture),
                sequence.ToString(CultureInfo.InvariantCulture),
                mid.ToString(CultureInfo.InvariantCulture));

            WriteAtomic(ResolvePath(PriceFileName, DefaultPriceFile), new[] { line });
        }

        private void WriteHistoryFile()
        {
            PublishedBar[] bars;
            lock (_sync)
                bars = _bars.Values.ToArray();

            if (bars.Length < 3)
                return;

            var lines = new List<string>(bars.Length + 1)
            {
                string.Join(";", HistoryVersion, Instrument)
            };

            foreach (var bar in bars)
            {
                lines.Add(string.Join(";",
                    new DateTimeOffset(bar.UtcMinute, TimeSpan.Zero).ToUnixTimeSeconds().ToString(CultureInfo.InvariantCulture),
                    bar.Open.ToString("0.########", CultureInfo.InvariantCulture),
                    bar.High.ToString("0.########", CultureInfo.InvariantCulture),
                    bar.Low.ToString("0.########", CultureInfo.InvariantCulture),
                    bar.Close.ToString("0.########", CultureInfo.InvariantCulture),
                    bar.Volume.ToString("0.####", CultureInfo.InvariantCulture)));
            }

            WriteAtomic(ResolvePath(HistoryFileName, DefaultHistoryFile), lines);
        }

        private string ResolvePath(string fileName, string fallback)
        {
            var folder = string.IsNullOrWhiteSpace(OutputFolder) ? DefaultFolder : OutputFolder;
            Directory.CreateDirectory(folder);
            return Path.Combine(folder, string.IsNullOrWhiteSpace(fileName) ? fallback : fileName);
        }

        // The monitor polls these files every 100 ms. Writing to a temporary file and
        // moving it into place keeps the reader from ever parsing a half-written row.
        private void WriteAtomic(string path, IEnumerable<string> lines)
        {
            var temp = path + ".tmp";
            using (var writer = new StreamWriter(temp, append: false))
            {
                foreach (var line in lines)
                    writer.WriteLine(line);
            }

            File.Move(temp, path, overwrite: true);
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

        private readonly record struct PublishedBar(
            DateTime UtcMinute,
            double Open,
            double High,
            double Low,
            double Close,
            double Volume)
        {
            public bool IsValid => Open > 0 && High >= Low && High > 0 && Low > 0 && Close > 0;
        }
    }
}
