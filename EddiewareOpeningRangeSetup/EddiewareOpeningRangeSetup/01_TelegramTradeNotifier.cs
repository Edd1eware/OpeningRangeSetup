using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
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

        public static void QueuePeriodicStatus(
            string folder,
            string series,
            DateTime utcSlot,
            string message)
        {
            var normalizedSlot = utcSlot.Kind == DateTimeKind.Utc
                ? utcSlot
                : utcSlot.ToUniversalTime();
            var safeSeries = SanitizeFileName(series);
            var slotKey = normalizedSlot.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture);
            var sentSlotsFile = Path.Combine(folder, $"telegram_{safeSeries}_sent_slots.txt");
            var pendingKey = sentSlotsFile + "|" + slotKey;

            lock (Sync)
            {
                if (PendingDates.Contains(pendingKey) || HasDateBeenSent(sentSlotsFile, slotKey))
                    return;

                PendingDates.Add(pendingKey);
            }

            _ = Task.Run(async () =>
            {
                try
                {
                    var credentials = ReadCredentials(Path.Combine(folder, "telegram_credentials.txt"));
                    if (credentials == null)
                    {
                        WriteDeliveryLog(folder, safeSeries, slotKey, "credentials_missing", null);
                        return;
                    }

                    long? messageId = null;
                    for (var attempt = 1; attempt <= 3 && !messageId.HasValue; attempt++)
                    {
                        messageId = await SendMessage(credentials.Token, credentials.ChatId, message)
                            .ConfigureAwait(false);
                        if (!messageId.HasValue && attempt < 3)
                            await Task.Delay(TimeSpan.FromSeconds(2 * attempt)).ConfigureAwait(false);
                    }

                    if (!messageId.HasValue)
                    {
                        WriteDeliveryLog(folder, safeSeries, slotKey, "send_failed", null);
                        return;
                    }

                    lock (Sync)
                    {
                        Directory.CreateDirectory(folder);
                        File.AppendAllText(sentSlotsFile, slotKey + Environment.NewLine);
                        File.AppendAllText(
                            Path.Combine(folder, "telegram_message_ids.txt"),
                            messageId.Value.ToString(CultureInfo.InvariantCulture) + Environment.NewLine);
                    }

                    WriteDeliveryLog(folder, safeSeries, slotKey, "sent", messageId);
                }
                catch (Exception ex)
                {
                    WriteDeliveryLog(folder, safeSeries, slotKey, "error:" + ex.GetType().Name, null);
                }
                finally
                {
                    lock (Sync)
                        PendingDates.Remove(pendingKey);
                }
            });
        }

        public static void QueuePhotoAlert(
            string folder,
            string series,
            DateTime utcSlot,
            string caption,
            string photoPath)
        {
            var normalizedSlot = utcSlot.Kind == DateTimeKind.Utc
                ? utcSlot
                : utcSlot.ToUniversalTime();
            var safeSeries = SanitizeFileName(series);
            var slotKey = normalizedSlot.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture);
            var sentSlotsFile = Path.Combine(folder, $"telegram_{safeSeries}_sent_slots.txt");
            var pendingKey = sentSlotsFile + "|" + slotKey;

            lock (Sync)
            {
                if (PendingDates.Contains(pendingKey) || HasDateBeenSent(sentSlotsFile, slotKey))
                    return;

                PendingDates.Add(pendingKey);
            }

            _ = Task.Run(async () =>
            {
                try
                {
                    var credentials = ReadCredentials(Path.Combine(folder, "telegram_credentials.txt"));
                    if (credentials == null)
                    {
                        WriteDeliveryLog(folder, safeSeries, slotKey, "credentials_missing", null);
                        return;
                    }

                    if (!File.Exists(photoPath))
                    {
                        WriteDeliveryLog(folder, safeSeries, slotKey, "photo_missing", null);
                        return;
                    }

                    long? messageId = null;
                    for (var attempt = 1; attempt <= 3 && !messageId.HasValue; attempt++)
                    {
                        messageId = await SendPhoto(
                                credentials.Token,
                                credentials.ChatId,
                                caption,
                                photoPath)
                            .ConfigureAwait(false);
                        if (!messageId.HasValue && attempt < 3)
                            await Task.Delay(TimeSpan.FromSeconds(2 * attempt)).ConfigureAwait(false);
                    }

                    if (!messageId.HasValue)
                    {
                        WriteDeliveryLog(folder, safeSeries, slotKey, "photo_send_failed", null);
                        return;
                    }

                    lock (Sync)
                    {
                        Directory.CreateDirectory(folder);
                        File.AppendAllText(sentSlotsFile, slotKey + Environment.NewLine);
                        File.AppendAllText(
                            Path.Combine(folder, "telegram_message_ids.txt"),
                            messageId.Value.ToString(CultureInfo.InvariantCulture) + Environment.NewLine);
                    }

                    WriteDeliveryLog(folder, safeSeries, slotKey, "photo_sent", messageId);
                }
                catch (Exception ex)
                {
                    WriteDeliveryLog(folder, safeSeries, slotKey, "photo_error:" + ex.GetType().Name, null);
                }
                finally
                {
                    lock (Sync)
                        PendingDates.Remove(pendingKey);
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

        private static string SanitizeFileName(string value)
        {
            if (string.IsNullOrWhiteSpace(value))
                return "periodic";

            foreach (var invalid in Path.GetInvalidFileNameChars())
                value = value.Replace(invalid, '_');

            return value.Trim();
        }

        private static void WriteDeliveryLog(
            string folder,
            string series,
            string slotKey,
            string result,
            long? messageId)
        {
            try
            {
                Directory.CreateDirectory(folder);
                var line = string.Join(";",
                    DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture),
                    slotKey,
                    result,
                    messageId?.ToString(CultureInfo.InvariantCulture) ?? "");
                File.AppendAllText(
                    Path.Combine(folder, $"telegram_{series}_delivery.csv"),
                    line + Environment.NewLine);
            }
            catch
            {
                // Notification diagnostics must never interrupt the indicator.
            }
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

        private static async Task<long?> SendPhoto(
            string token,
            string chatId,
            string caption,
            string photoPath)
        {
            var url = $"https://api.telegram.org/bot{token}/sendPhoto";
            using var content = new MultipartFormDataContent();
            content.Add(new StringContent(chatId), "chat_id");
            content.Add(new StringContent(caption), "caption");

            var photoBytes = await File.ReadAllBytesAsync(photoPath).ConfigureAwait(false);
            using var photo = new ByteArrayContent(photoBytes);
            photo.Headers.ContentType = new MediaTypeHeaderValue("image/png");
            content.Add(photo, "photo", Path.GetFileName(photoPath));

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
