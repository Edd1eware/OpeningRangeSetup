using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;

namespace ATAS.Indicators
{
    internal static class TelegramTradeNotifier
    {
        private static readonly object Sync = new object();
        private static readonly HttpClient Client = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(15)
        };
        private static readonly HashSet<string> PendingDates = new HashSet<string>(StringComparer.Ordinal);

        public static void QueueTerminalResult(string folder, DateTime nyDate, string message)
        {
            var dateKey = nyDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
            var sentDatesFile = Path.Combine(folder, "telegram_sent_dates.txt");

            lock (Sync)
            {
                if (PendingDates.Contains(dateKey) || HasDateBeenSent(sentDatesFile, dateKey))
                    return;

                PendingDates.Add(dateKey);
            }

            _ = Task.Run(async () =>
            {
                try
                {
                    var credentials = ReadCredentials(Path.Combine(folder, "telegram_credentials.txt"));
                    if (credentials == null)
                        return;

                    var messageId = await SendMessage(credentials.Token, credentials.ChatId, message).ConfigureAwait(false);
                    if (!messageId.HasValue)
                        return;

                    lock (Sync)
                    {
                        Directory.CreateDirectory(folder);
                        File.AppendAllText(sentDatesFile, dateKey + Environment.NewLine);
                        File.AppendAllText(
                            Path.Combine(folder, "telegram_message_ids.txt"),
                            messageId.Value.ToString(CultureInfo.InvariantCulture) + Environment.NewLine);
                    }
                }
                catch
                {
                    // Telegram must never interrupt indicator calculation or CSV export.
                }
                finally
                {
                    lock (Sync)
                        PendingDates.Remove(dateKey);
                }
            });
        }

        private static bool HasDateBeenSent(string path, string dateKey)
        {
            if (!File.Exists(path))
                return false;

            try
            {
                foreach (var line in File.ReadLines(path))
                {
                    if (string.Equals(line.Trim(), dateKey, StringComparison.Ordinal))
                        return true;
                }
            }
            catch
            {
                return false;
            }

            return false;
        }

        private static Credentials? ReadCredentials(string path)
        {
            if (!File.Exists(path))
                return null;

            var token = "";
            var chatId = "";

            foreach (var rawLine in File.ReadLines(path))
            {
                var line = rawLine.Trim();
                if (line.Length == 0 || line.StartsWith("#", StringComparison.Ordinal))
                    continue;

                var separator = line.IndexOf('=');
                if (separator <= 0)
                    continue;

                var key = line.Substring(0, separator).Trim();
                var value = line.Substring(separator + 1).Trim();

                if (key.Equals("token", StringComparison.OrdinalIgnoreCase))
                    token = value;
                else if (key.Equals("chat_id", StringComparison.OrdinalIgnoreCase))
                    chatId = value;
            }

            return token.Length == 0 || chatId.Length == 0
                ? null
                : new Credentials(token, chatId);
        }

        private static async Task<long?> SendMessage(string token, string chatId, string message)
        {
            var url = $"https://api.telegram.org/bot{token}/sendMessage";
            using var content = new FormUrlEncodedContent(new Dictionary<string, string>
            {
                ["chat_id"] = chatId,
                ["text"] = message
            });
            using var response = await Client.PostAsync(url, content).ConfigureAwait(false);

            if (!response.IsSuccessStatusCode)
                return null;

            var json = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
            using var document = JsonDocument.Parse(json);
            var root = document.RootElement;

            if (!root.TryGetProperty("ok", out var ok) || !ok.GetBoolean())
                return null;

            if (!root.TryGetProperty("result", out var result) ||
                !result.TryGetProperty("message_id", out var messageId))
            {
                return null;
            }

            return messageId.GetInt64();
        }

        private sealed class Credentials
        {
            public Credentials(string token, string chatId)
            {
                Token = token;
                ChatId = chatId;
            }

            public string Token { get; }
            public string ChatId { get; }
        }
    }
}
