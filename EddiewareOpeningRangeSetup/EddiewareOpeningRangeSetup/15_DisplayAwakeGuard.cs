using System;
using System.Runtime.InteropServices;
using System.Threading;

namespace ATAS.Indicators
{
    internal sealed class DisplayAwakeGuard : IDisposable
    {
        private readonly ManualResetEventSlim _stop = new(false);
        private readonly Thread _thread;
        private bool _disposed;

        public DisplayAwakeGuard()
        {
            _thread = new Thread(KeepAwakeLoop)
            {
                IsBackground = true,
                Name = "ATAS-MT5 Display Awake Guard"
            };
            _thread.Start();
        }

        public void Dispose()
        {
            if (_disposed)
                return;

            _disposed = true;
            _stop.Set();
            try { _thread.Join(TimeSpan.FromSeconds(2)); }
            catch { }
            _stop.Dispose();
        }

        private void KeepAwakeLoop()
        {
            try
            {
                while (!_stop.IsSet)
                {
                    SetThreadExecutionState(
                        ExecutionState.Continuous |
                        ExecutionState.SystemRequired |
                        ExecutionState.DisplayRequired);
                    _stop.Wait(TimeSpan.FromSeconds(30));
                }
            }
            finally
            {
                SetThreadExecutionState(ExecutionState.Continuous);
            }
        }

        [Flags]
        private enum ExecutionState : uint
        {
            SystemRequired = 0x00000001,
            DisplayRequired = 0x00000002,
            Continuous = 0x80000000
        }

        [DllImport("kernel32.dll")]
        private static extern ExecutionState SetThreadExecutionState(ExecutionState executionState);
    }
}
