using System.Net;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using Gulong.ShortDrama.Core;
using Gulong.ShortDrama.Models;
using Microsoft.Web.WebView2.Core;

namespace Gulong.ShortDrama.Services;

public sealed class OfficialApiClient : IDisposable
{
    public const string OfficialOrigin = "https://sologle.com";

    private readonly CookieContainer _cookies = new();
    private readonly HttpClient _httpClient;

    public OfficialApiClient()
    {
        var handler = new HttpClientHandler
        {
            CookieContainer = _cookies,
            UseCookies = true,
            AutomaticDecompression = DecompressionMethods.All,
        };
        _httpClient = new HttpClient(handler)
        {
            BaseAddress = new Uri(OfficialOrigin),
            Timeout = TimeSpan.FromSeconds(30),
        };
        _httpClient.DefaultRequestHeaders.UserAgent.ParseAdd("Gulong-ShortDrama-Native/2.0 (Windows)");
        _httpClient.DefaultRequestHeaders.Accept.ParseAdd("application/json");
    }

    public async Task ImportBrowserCookiesAsync(CoreWebView2 browser)
    {
        var browserCookies = await browser.CookieManager.GetCookiesAsync(OfficialOrigin);
        var origin = new Uri(OfficialOrigin);
        foreach (var source in browserCookies)
        {
            var cookie = new Cookie(source.Name, source.Value, string.IsNullOrWhiteSpace(source.Path) ? "/" : source.Path, origin.Host)
            {
                HttpOnly = source.IsHttpOnly,
                Secure = source.IsSecure,
            };
            if (!source.IsSession && source.Expires > DateTime.MinValue)
            {
                cookie.Expires = source.Expires.ToUniversalTime();
            }
            _cookies.Add(origin, cookie);
        }
    }

    public async Task<ApiResult<UserAccount>> ReadAccountAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            var me = await SendAsync(HttpMethod.Get, "/api/auth/me", null, null, cancellationToken);
            if (!me.IsSuccessStatusCode)
            {
                return ApiResult<UserAccount>.Failure(ReadCode(me.Body, "AUTH_REQUIRED"), ReadMessage(me.Body, "请先登录古龙账号"));
            }

            using var meDocument = JsonDocument.Parse(me.Body);
            if (!TryGetObject(meDocument.RootElement, "user", out var user))
            {
                return ApiResult<UserAccount>.Failure("AUTH_REQUIRED", "请先登录古龙账号");
            }

            var billingTask = SendAsync(HttpMethod.Get, "/api/billing/subscription", null, null, cancellationToken);
            var dashboardTask = SendAsync(HttpMethod.Get, "/api/account/dashboard", null, null, cancellationToken);
            await Task.WhenAll(billingTask, dashboardTask);

            using var billingDocument = TryParse(billingTask.Result.Body);
            using var dashboardDocument = TryParse(dashboardTask.Result.Body);
            var billingRoot = billingDocument?.RootElement;
            var dashboardRoot = dashboardDocument?.RootElement;

            var displayName = ReadString(user, "displayName", "username", "email") ?? "古龙用户";
            var username = ReadString(user, "username");
            var email = ReadString(user, "email");
            var balanceFen = ReadInt64(dashboardRoot, "balanceFen") ?? ReadInt64(billingRoot, "balanceFen") ?? 0;
            var subscriptionStatus = ReadNestedString(billingRoot, "subscription", "status");
            var isMember = ReadBoolean(billingRoot, "isMember") ?? string.Equals(subscriptionStatus, "active", StringComparison.OrdinalIgnoreCase);

            return ApiResult<UserAccount>.Success(new UserAccount(displayName, username, email, balanceFen, isMember, subscriptionStatus));
        }
        catch (Exception error) when (error is HttpRequestException or TaskCanceledException or JsonException)
        {
            return ApiResult<UserAccount>.Failure("NETWORK_ERROR", error is TaskCanceledException ? "连接古龙官网超时，请检查网络" : $"无法连接古龙官网：{error.Message}");
        }
    }

    public async Task<ApiResult<TaskCreationResult>> CreateVideoTaskAsync(H3TaskRequest request, CancellationToken cancellationToken = default)
    {
        try
        {
            var response = await SendAsync(HttpMethod.Post, "/api/h3/tasks", request, TaskContracts.CreateIdempotencyKey(), cancellationToken);
            if (!response.IsSuccessStatusCode)
            {
                return ApiResult<TaskCreationResult>.Failure(ReadCode(response.Body, "TASK_CREATE_FAILED"), ReadMessage(response.Body, "官网未能创建视频任务"));
            }

            using var document = JsonDocument.Parse(response.Body);
            var root = document.RootElement;
            var taskElement = TryGetObject(root, "task", out var taskObject) ? taskObject : root;
            var task = ParseTask(taskElement);
            var chargedFen = ReadNestedInt64(root, "billing", "chargedFen") ?? task.PriceFen;
            var remainingBalanceFen = ReadNestedInt64(root, "billing", "remainingBalanceFen") ?? 0;
            return ApiResult<TaskCreationResult>.Success(new TaskCreationResult(task, chargedFen, remainingBalanceFen));
        }
        catch (Exception error) when (error is HttpRequestException or TaskCanceledException or JsonException)
        {
            return ApiResult<TaskCreationResult>.Failure("NETWORK_ERROR", error is TaskCanceledException ? "提交任务超时，请稍后重试" : $"提交任务失败：{error.Message}");
        }
    }

    public async Task<ApiResult<IReadOnlyList<VideoTask>>> ListVideoTasksAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            var response = await SendAsync(HttpMethod.Get, "/api/h3/tasks", null, null, cancellationToken);
            if (!response.IsSuccessStatusCode)
            {
                return ApiResult<IReadOnlyList<VideoTask>>.Failure(ReadCode(response.Body, "TASK_LIST_FAILED"), ReadMessage(response.Body, "无法读取视频任务"));
            }

            using var document = JsonDocument.Parse(response.Body);
            if (!document.RootElement.TryGetProperty("tasks", out var tasks) || tasks.ValueKind != JsonValueKind.Array)
            {
                return ApiResult<IReadOnlyList<VideoTask>>.Success([]);
            }

            return ApiResult<IReadOnlyList<VideoTask>>.Success(tasks.EnumerateArray().Select(ParseTask).ToArray());
        }
        catch (Exception error) when (error is HttpRequestException or TaskCanceledException or JsonException)
        {
            return ApiResult<IReadOnlyList<VideoTask>>.Failure("NETWORK_ERROR", error is TaskCanceledException ? "读取任务超时，请稍后重试" : $"读取任务失败：{error.Message}");
        }
    }

    private async Task<RawResponse> SendAsync(HttpMethod method, string path, object? body, string? idempotencyKey, CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(method, path);
        if (body is not null) request.Content = JsonContent.Create(body);
        if (!string.IsNullOrWhiteSpace(idempotencyKey)) request.Headers.Add("Idempotency-Key", idempotencyKey);
        using var response = await _httpClient.SendAsync(request, cancellationToken);
        return new RawResponse(response.IsSuccessStatusCode, (int)response.StatusCode, await response.Content.ReadAsStringAsync(cancellationToken));
    }

    private static VideoTask ParseTask(JsonElement task)
    {
        var id = ReadString(task, "id", "_id") ?? string.Empty;
        var orderNo = ReadString(task, "orderNo", "order_no") ?? id;
        var createdText = ReadString(task, "createdAt", "created_at");
        DateTimeOffset? createdAt = DateTimeOffset.TryParse(createdText, out var parsed) ? parsed : null;
        return new VideoTask(
            id,
            orderNo,
            ReadString(task, "prompt") ?? string.Empty,
            ReadString(task, "status") ?? "queued",
            ReadString(task, "aspectRatio", "aspect_ratio") ?? "9:16",
            (int)(ReadInt64(task, "durationSeconds", "duration_seconds") ?? 0),
            ReadInt64(task, "priceFen", "price_fen") ?? 0,
            createdAt);
    }

    private static JsonDocument? TryParse(string text)
    {
        try { return string.IsNullOrWhiteSpace(text) ? null : JsonDocument.Parse(text); }
        catch (JsonException) { return null; }
    }

    private static bool TryGetObject(JsonElement element, string name, out JsonElement value)
    {
        if (element.ValueKind == JsonValueKind.Object && element.TryGetProperty(name, out value) && value.ValueKind == JsonValueKind.Object) return true;
        value = default;
        return false;
    }

    private static string ReadCode(string body, string fallback)
    {
        using var document = TryParse(body);
        return document is null ? fallback : ReadString(document.RootElement, "code") ?? fallback;
    }

    private static string ReadMessage(string body, string fallback)
    {
        using var document = TryParse(body);
        return document is null ? fallback : ReadString(document.RootElement, "message", "detail") ?? fallback;
    }

    private static string? ReadString(JsonElement element, params string[] names)
    {
        if (element.ValueKind != JsonValueKind.Object) return null;
        foreach (var name in names)
        {
            if (element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String) return value.GetString();
        }
        return null;
    }

    private static long? ReadInt64(JsonElement? element, params string[] names)
    {
        if (!element.HasValue || element.Value.ValueKind != JsonValueKind.Object) return null;
        return ReadInt64(element.Value, names);
    }

    private static long? ReadInt64(JsonElement element, params string[] names)
    {
        if (element.ValueKind != JsonValueKind.Object) return null;
        foreach (var name in names)
        {
            if (!element.TryGetProperty(name, out var value)) continue;
            if (value.ValueKind == JsonValueKind.Number && value.TryGetInt64(out var number)) return number;
            if (value.ValueKind == JsonValueKind.String && long.TryParse(value.GetString(), out number)) return number;
        }
        return null;
    }

    private static bool? ReadBoolean(JsonElement? element, string name)
    {
        if (!element.HasValue || element.Value.ValueKind != JsonValueKind.Object || !element.Value.TryGetProperty(name, out var value)) return null;
        return value.ValueKind is JsonValueKind.True or JsonValueKind.False ? value.GetBoolean() : null;
    }

    private static string? ReadNestedString(JsonElement? element, string parent, string child)
    {
        return element.HasValue && TryGetObject(element.Value, parent, out var nested) ? ReadString(nested, child) : null;
    }

    private static long? ReadNestedInt64(JsonElement element, string parent, string child)
    {
        return TryGetObject(element, parent, out var nested) ? ReadInt64(nested, child) : null;
    }

    public void Dispose() => _httpClient.Dispose();

    private sealed record RawResponse(bool IsSuccessStatusCode, int StatusCode, string Body);
}
