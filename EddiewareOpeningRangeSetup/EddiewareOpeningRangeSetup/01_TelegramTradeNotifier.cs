using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text.Json;
using System.Threading;
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

        // Long polling needs its own client: getUpdates holds the connection open for
        // PollTimeoutSeconds, which is longer than the 15s outbound timeout above.
        private static readonly HttpClient PollClient = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(PollTimeoutSeconds + 20)
        };

        private const int PollTimeoutSeconds = 25;
        private const int CommandCooldownSeconds = 3;

        private static int _commandListenerStarted;

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
            string message,
            int repetitions = 1)
        {
            var requestedCopies = Math.Clamp(repetitions, 1, 20);
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

                    var sentCopies = 0;
                    long? lastMessageId = null;
                    for (var copy = 1; copy <= requestedCopies; copy++)
                    {
                        long? messageId = null;
                        for (var attempt = 1; attempt <= 3 && !messageId.HasValue; attempt++)
                        {
                            messageId = await SendMessage(credentials.Token, credentials.ChatId, message)
                                .ConfigureAwait(false);
                            if (!messageId.HasValue && attempt < 3)
                                await Task.Delay(TimeSpan.FromSeconds(2 * attempt)).ConfigureAwait(false);
                        }

                        if (messageId.HasValue)
                        {
                            sentCopies++;
                            lastMessageId = messageId;
                            AppendMessageId(folder, messageId.Value);
                            WriteDeliveryLog(
                                folder,
                                safeSeries,
                                slotKey,
                                $"sent_{copy:00}_of_{requestedCopies:00}",
                                messageId);
                        }
                        else
                        {
                            WriteDeliveryLog(
                                folder,
                                safeSeries,
                                slotKey,
                                $"send_failed_{copy:00}_of_{requestedCopies:00}",
                                null);
                        }

                        if (copy < requestedCopies)
                            await Task.Delay(TimeSpan.FromMilliseconds(1100)).ConfigureAwait(false);
                    }

                    if (sentCopies != requestedCopies)
                    {
                        WriteDeliveryLog(
                            folder,
                            safeSeries,
                            slotKey,
                            $"burst_incomplete_{sentCopies:00}_of_{requestedCopies:00}",
                            lastMessageId);
                        return;
                    }

                    lock (Sync)
                    {
                        Directory.CreateDirectory(folder);
                        File.AppendAllText(sentSlotsFile, slotKey + Environment.NewLine);
                    }

                    WriteDeliveryLog(
                        folder,
                        safeSeries,
                        slotKey,
                        $"burst_sent_{requestedCopies:00}",
                        lastMessageId);
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
            string photoPath,
            int repetitions = 1)
        {
            var requestedCopies = Math.Clamp(repetitions, 1, 20);
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

                    var sentCopies = 0;
                    long? lastMessageId = null;
                    for (var copy = 1; copy <= requestedCopies; copy++)
                    {
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

                        if (messageId.HasValue)
                        {
                            sentCopies++;
                            lastMessageId = messageId;
                            AppendMessageId(folder, messageId.Value);
                            WriteDeliveryLog(
                                folder,
                                safeSeries,
                                slotKey,
                                $"photo_sent_{copy:00}_of_{requestedCopies:00}",
                                messageId);
                        }
                        else
                        {
                            WriteDeliveryLog(
                                folder,
                                safeSeries,
                                slotKey,
                                $"photo_failed_{copy:00}_of_{requestedCopies:00}",
                                null);
                        }

                        if (copy < requestedCopies)
                            await Task.Delay(TimeSpan.FromMilliseconds(1100)).ConfigureAwait(false);
                    }

                    if (sentCopies != requestedCopies)
                    {
                        WriteDeliveryLog(
                            folder,
                            safeSeries,
                            slotKey,
                            $"photo_burst_incomplete_{sentCopies:00}_of_{requestedCopies:00}",
                            lastMessageId);
                        return;
                    }

                    lock (Sync)
                    {
                        Directory.CreateDirectory(folder);
                        File.AppendAllText(sentSlotsFile, slotKey + Environment.NewLine);
                    }

                    WriteDeliveryLog(
                        folder,
                        safeSeries,
                        slotKey,
                        $"photo_burst_sent_{requestedCopies:00}",
                        lastMessageId);
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

        // Starts the inbound command poller once per process. Any indicator may call it
        // on every OnInitialize: the interlock keeps a single getUpdates loop alive, which
        // matters because Telegram rejects concurrent pollers on the same bot token.
        public static void EnsureScreenshotCommandListener(string folder, Func<string?> captureScreenshot)
        {
            if (captureScreenshot == null)
                return;

            if (Interlocked.Exchange(ref _commandListenerStarted, 1) == 1)
                return;

            _ = Task.Run(() => CommandLoop(folder, captureScreenshot));
        }

        private static async Task CommandLoop(string folder, Func<string?> captureScreenshot)
        {
            long offset = 0;
            var lastHandledUtc = DateTime.MinValue;

            while (true)
            {
                try
                {
                    var credentials = ReadCredentials(Path.Combine(folder, "telegram_credentials.txt"));
                    if (credentials == null)
                    {
                        await Task.Delay(TimeSpan.FromSeconds(30)).ConfigureAwait(false);
                        continue;
                    }

                    // Drop whatever piled up while ATAS was closed: an "s" typed hours ago
                    // must not fire a screenshot of an unrelated chart state.
                    if (offset == 0)
                    {
                        offset = await ResolveStartOffset(credentials.Token).ConfigureAwait(false);
                        WriteCommandLog(folder, "listener_started", null);
                        continue;
                    }

                    var updates = await FetchUpdates(credentials.Token, offset).ConfigureAwait(false);
                    foreach (var update in updates)
                    {
                        offset = update.UpdateId + 1;

                        // Only the configured chat may drive the terminal.
                        if (!string.Equals(update.ChatId, credentials.ChatId, StringComparison.Ordinal))
                        {
                            WriteCommandLog(folder, "chat_rejected", update.Text);
                            continue;
                        }

                        if (!IsScreenshotCommand(update.Text))
                            continue;

                        if ((DateTime.UtcNow - lastHandledUtc).TotalSeconds < CommandCooldownSeconds)
                        {
                            WriteCommandLog(folder, "cooldown_skipped", update.Text);
                            continue;
                        }

                        lastHandledUtc = DateTime.UtcNow;
                        await HandleScreenshotCommand(
                                folder,
                                credentials,
                                captureScreenshot)
                            .ConfigureAwait(false);
                    }
                }
                catch (Exception ex)
                {
                    WriteCommandLog(folder, "loop_error:" + ex.GetType().Name, null);
                    await Task.Delay(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
                }
            }
        }

        private static bool IsScreenshotCommand(string text)
        {
            if (string.IsNullOrWhiteSpace(text))
                return false;

            var value = text.Trim();
            if (value.StartsWith("/", StringComparison.Ordinal))
                value = value.Substring(1);

            // "/s@BotName" when the bot sits in a group.
            var at = value.IndexOf('@');
            if (at > 0)
                value = value.Substring(0, at);

            return value.Equals("s", StringComparison.OrdinalIgnoreCase);
        }

        private static async Task HandleScreenshotCommand(
            string folder,
            Credentials credentials,
            Func<string?> captureScreenshot)
        {
            string? photoPath = null;
            try
            {
                photoPath = captureScreenshot();
            }
            catch (Exception ex)
            {
                WriteCommandLog(folder, "capture_error:" + ex.GetType().Name, null);
            }

            if (string.IsNullOrWhiteSpace(photoPath) || !File.Exists(photoPath))
            {
                await SendMessage(
                        credentials.Token,
                        credentials.ChatId,
                        "No se pudo capturar la ventana de ATAS.")
                    .ConfigureAwait(false);
                WriteCommandLog(folder, "capture_failed", null);
                return;
            }

            var caption = "Captura ATAS a solicitud · " +
                          DateTime.UtcNow.ToString("yyyy-MM-dd HH:mm:ss 'UTC'", CultureInfo.InvariantCulture);

            long? messageId = null;
            for (var attempt = 1; attempt <= 3 && !messageId.HasValue; attempt++)
            {
                messageId = await SendPhoto(credentials.Token, credentials.ChatId, caption, photoPath)
                    .ConfigureAwait(false);
                if (!messageId.HasValue && attempt < 3)
                    await Task.Delay(TimeSpan.FromSeconds(2 * attempt)).ConfigureAwait(false);
            }

            if (messageId.HasValue)
            {
                AppendMessageId(folder, messageId.Value);
                WriteCommandLog(folder, "screenshot_sent", messageId.Value.ToString(CultureInfo.InvariantCulture));
            }
            else
            {
                WriteCommandLog(folder, "screenshot_send_failed", null);
            }
        }

        private static async Task<long> ResolveStartOffset(string token)
        {
            var url = $"https://api.telegram.org/bot{token}/getUpdates?offset=-1&timeout=0";
            using var response = await PollClient.GetAsync(url).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
                return 1;

            var json = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
            using var document = JsonDocument.Parse(json);
            var root = document.RootElement;
            if (!root.TryGetProperty("ok", out var ok) || !ok.GetBoolean())
                return 1;

            if (!root.TryGetProperty("result", out var result) || result.GetArrayLength() == 0)
                return 1;

            var last = result[result.GetArrayLength() - 1];
            return last.TryGetProperty("update_id", out var updateId)
                ? updateId.GetInt64() + 1
                : 1;
        }

        private static async Task<List<TelegramCommand>> FetchUpdates(string token, long offset)
        {
            var commands = new List<TelegramCommand>();
            var url = $"https://api.telegram.org/bot{token}/getUpdates" +
                      $"?offset={offset.ToString(CultureInfo.InvariantCulture)}" +
                      $"&timeout={PollTimeoutSeconds.ToString(CultureInfo.InvariantCulture)}" +
                      "&allowed_updates=%5B%22message%22%5D";

            using var response = await PollClient.GetAsync(url).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
                return commands;

            var json = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
            using var document = JsonDocument.Parse(json);
            var root = document.RootElement;
            if (!root.TryGetProperty("ok", out var ok) || !ok.GetBoolean())
                return commands;

            if (!root.TryGetProperty("result", out var result) ||
                result.ValueKind != JsonValueKind.Array)
            {
                return commands;
            }

            foreach (var update in result.EnumerateArray())
            {
                if (!update.TryGetProperty("update_id", out var updateIdElement))
                    continue;

                var updateId = updateIdElement.GetInt64();
                var text = "";
                var chatId = "";

                if (update.TryGetProperty("message", out var message))
                {
                    if (message.TryGetProperty("text", out var textElement) &&
                        textElement.ValueKind == JsonValueKind.String)
                    {
                        text = textElement.GetString() ?? "";
                    }

                    if (message.TryGetProperty("chat", out var chat) &&
                        chat.TryGetProperty("id", out var chatIdElement))
                    {
                        chatId = chatIdElement.ValueKind == JsonValueKind.String
                            ? chatIdElement.GetString() ?? ""
                            : chatIdElement.GetRawText();
                    }
                }

                commands.Add(new TelegramCommand(updateId, chatId, text));
            }

            return commands;
        }

        private static void WriteCommandLog(string folder, string result, string? detail)
        {
            try
            {
                Directory.CreateDirectory(folder);
                var line = string.Join(";",
                    DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture),
                    result,
                    (detail ?? "").Replace(';', ',').Replace('\n', ' ').Replace('\r', ' '));
                File.AppendAllText(
                    Path.Combine(folder, "telegram_commands.csv"),
                    line + Environment.NewLine);
            }
            catch
            {
                // Command diagnostics must never interrupt the indicator.
            }
        }

        private readonly record struct TelegramCommand(long UpdateId, string ChatId, string Text);

        private static void AppendMessageId(string folder, long messageId)
        {
            lock (Sync)
            {
                Directory.CreateDirectory(folder);
                File.AppendAllText(
                    Path.Combine(folder, "telegram_message_ids.txt"),
                    messageId.ToString(CultureInfo.InvariantCulture) + Environment.NewLine);
            }
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
