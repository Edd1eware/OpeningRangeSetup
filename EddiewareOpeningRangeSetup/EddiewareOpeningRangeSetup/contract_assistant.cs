using System;
using ATAS.DataFeedsCore;

namespace ATAS.Indicators
{
    internal sealed class ContractAssistant
    {
        public sealed class Split
        {
            public int TotalContracts { get; set; }
            public int PartialContracts { get; set; }
            public int RunnerContracts { get; set; }
            public bool HasPartial => PartialContracts > 0 && RunnerContracts > 0;
        }

        public sealed class StartRequest
        {
            public Portfolio? Portfolio { get; set; }
            public Security? Security { get; set; }
            public string Side { get; set; } = "";
            public decimal EntryPrice { get; set; }
            public decimal TpPrice { get; set; }
            public int Contracts { get; set; }
        }

        public sealed class ManageRequest
        {
            public Portfolio? Portfolio { get; set; }
            public Security? Security { get; set; }
            public Order? StopOrder { get; set; }
            public decimal CurrentPosition { get; set; }
            public decimal BreakevenOffsetTicks { get; set; }
            public decimal TickSize { get; set; }
        }

        public sealed class ManageResult
        {
            public bool MoveStopToBreakeven { get; set; }
            public Order? NewStopOrder { get; set; }
            public int ActiveContracts { get; set; }
        }

        private Split _split = new Split();
        private string _side = "";
        private decimal _entryPrice;
        private bool _breakevenMoved;

        public Order? PartialTpOrder { get; private set; }
        public bool IsActive => _split.TotalContracts > 0;
        public bool HasWorkingPartialTp => PartialTpOrder != null && PartialTpOrder.State == OrderStates.Active;

        public static Split CalculateSplit(int contracts)
        {
            if (contracts <= 1)
            {
                return new Split
                {
                    TotalContracts = Math.Max(contracts, 0),
                    PartialContracts = 0,
                    RunnerContracts = Math.Max(contracts, 0)
                };
            }

            var runner = contracts / 2;
            var partial = contracts - runner;

            return new Split
            {
                TotalContracts = contracts,
                PartialContracts = partial,
                RunnerContracts = runner
            };
        }

        public Order? Start(StartRequest request)
        {
            Reset();

            if (request.Contracts <= 0 || request.TpPrice <= 0)
                return null;

            _split = CalculateSplit(request.Contracts);
            _side = request.Side;
            _entryPrice = request.EntryPrice;

            if (!_split.HasPartial || request.Portfolio == null || request.Security == null)
                return null;

            var exitDirection = request.Side == "BUY"
                ? OrderDirections.Sell
                : OrderDirections.Buy;

            PartialTpOrder = new Order
            {
                Portfolio = request.Portfolio,
                Security = request.Security,
                Direction = exitDirection,
                Type = OrderTypes.Limit,
                Price = request.TpPrice,
                QuantityToFill = _split.PartialContracts,
                Comment = $"EW_contract_assistant_TP_{_split.PartialContracts}c"
            };

            return PartialTpOrder;
        }

        public ManageResult Manage(ManageRequest request)
        {
            var result = new ManageResult
            {
                ActiveContracts = _split.TotalContracts
            };

            if (!IsActive || _breakevenMoved || !_split.HasPartial || request.StopOrder == null)
                return result;

            var remaining = (int)Math.Abs(request.CurrentPosition);
            if (remaining <= 0 || remaining > _split.RunnerContracts)
                return result;

            if (request.Portfolio == null || request.Security == null)
                return result;

            var bePrice = _side == "BUY"
                ? _entryPrice + request.BreakevenOffsetTicks * request.TickSize
                : _entryPrice - request.BreakevenOffsetTicks * request.TickSize;

            var stopPrice = request.StopOrder.TriggerPrice;
            if (stopPrice <= 0)
                stopPrice = bePrice;

            var protectedPrice = _side == "BUY"
                ? Math.Max(stopPrice, bePrice)
                : Math.Min(stopPrice, bePrice);

            result.NewStopOrder = new Order
            {
                Portfolio = request.Portfolio,
                Security = request.Security,
                Direction = request.StopOrder.Direction,
                Type = OrderTypes.Stop,
                TriggerPrice = protectedPrice,
                QuantityToFill = remaining,
                Comment = "EW_contract_assistant_BE"
            };
            result.MoveStopToBreakeven = true;
            result.ActiveContracts = remaining;
            _breakevenMoved = true;
            return result;
        }

        public void Reset()
        {
            _split = new Split();
            _side = "";
            _entryPrice = 0;
            _breakevenMoved = false;
            PartialTpOrder = null;
        }
    }
}
