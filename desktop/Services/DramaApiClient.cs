using System.Net;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.IO;
using Gulong.ShortDrama.Models;

namespace Gulong.ShortDrama.Services;

public sealed class DramaApiClient : IDisposable
{
    public const string DramaOrigin = "https://aipdd-drameclaw-new.vercel.app";

    private readonly CookieContainer _cookies = new();
    private readonly HttpClient _httpClient;

    public DramaApiClient()
    {
        var handler = new HttpClientHandler
        {
            CookieContainer = _cookies,
            UseCookies = true,
            AutomaticDecompression = DecompressionMethods.All,
        };
        _httpClient = new HttpClient(handler)
        {
            BaseAddress = new Uri(DramaOrigin),
            Timeout = TimeSpan.FromMinutes(4),
        };
        _httpClient.DefaultRequestHeaders.UserAgent.ParseAdd("Gulong-ShortDrama-Native/3.0 (Windows)");
        _httpClient.DefaultRequestHeaders.Accept.ParseAdd("application/json");
    }

    public async Task<ApiResult<JsonElement>> ExchangeGulongSessionAsync(string token, CancellationToken cancellationToken = default)
    {
        return await SendJsonAsync(HttpMethod.Post, "/api/v1/auth/gulong/exchange", new { token }, cancellationToken);
    }

    public Task<ApiResult<JsonElement>> GetAsync(string path, CancellationToken cancellationToken = default) =>
        SendJsonAsync(HttpMethod.Get, path, null, cancellationToken);

    public Task<ApiResult<JsonElement>> PostAsync(string path, object? body = null, CancellationToken cancellationToken = default) =>
        SendJsonAsync(HttpMethod.Post, path, body ?? new { }, cancellationToken);

    public Task<ApiResult<JsonElement>> PutAsync(string path, object? body = null, CancellationToken cancellationToken = default) =>
        SendJsonAsync(HttpMethod.Put, path, body ?? new { }, cancellationToken);

    public Task<ApiResult<JsonElement>> PatchAsync(string path, object? body = null, CancellationToken cancellationToken = default) =>
        SendJsonAsync(HttpMethod.Patch, path, body ?? new { }, cancellationToken);

    public Task<ApiResult<JsonElement>> DeleteAsync(string path, CancellationToken cancellationToken = default) =>
        SendJsonAsync(HttpMethod.Delete, path, null, cancellationToken);

    public async Task<ApiResult<JsonElement>> UploadFileAsync(
        string path,
        string filePath,
        IReadOnlyDictionary<string, string>? fields = null,
        CancellationToken cancellationToken = default)
    {
        try
        {
            await using var stream = File.OpenRead(filePath);
            using var content = new MultipartFormDataContent();
            var fileContent = new StreamContent(stream);
            content.Add(fileContent, "file", Path.GetFileName(filePath));
            if (fields is not null)
            {
                foreach (var field in fields) content.Add(new StringContent(field.Value), field.Key);
            }
            using var response = await _httpClient.PostAsync(NormalizePath(path), content, cancellationToken);
            return await ParseResponseAsync(response, cancellationToken);
        }
        catch (Exception error) when (error is HttpRequestException or TaskCanceledException or IOException or JsonException)
        {
            return ApiResult<JsonElement>.Failure("UPLOAD_FAILED", error is TaskCanceledException ? "上传超时，请稍后重试" : $"上传失败：{error.Message}");
        }
    }

    public async Task<ApiResult<string>> DownloadAsync(string path, string targetPath, CancellationToken cancellationToken = default)
    {
        return await DownloadCoreAsync(HttpMethod.Get, path, targetPath, cancellationToken);
    }

    public async Task<ApiResult<string>> DownloadPostAsync(string path, string targetPath, CancellationToken cancellationToken = default)
    {
        return await DownloadCoreAsync(HttpMethod.Post, path, targetPath, cancellationToken);
    }

    private async Task<ApiResult<string>> DownloadCoreAsync(HttpMethod method, string path, string targetPath, CancellationToken cancellationToken)
    {
        try
        {
            using var request = new HttpRequestMessage(method, NormalizePath(path));
            if (method == HttpMethod.Post) request.Content = JsonContent.Create(new { });
            using var response = await _httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
            if (!response.IsSuccessStatusCode)
            {
                var body = await response.Content.ReadAsStringAsync(cancellationToken);
                return ApiResult<string>.Failure($"HTTP_{(int)response.StatusCode}", ReadError(body, "下载失败"));
            }
            await using var source = await response.Content.ReadAsStreamAsync(cancellationToken);
            await using var target = File.Create(targetPath);
            await source.CopyToAsync(target, cancellationToken);
            return ApiResult<string>.Success(targetPath);
        }
        catch (Exception error) when (error is HttpRequestException or TaskCanceledException or IOException)
        {
            return ApiResult<string>.Failure("DOWNLOAD_FAILED", error is TaskCanceledException ? "下载超时" : $"下载失败：{error.Message}");
        }
    }

    public Uri ResolveUri(string path)
    {
        if (Uri.TryCreate(path, UriKind.Absolute, out var absolute)) return absolute;
        return new Uri(new Uri(DramaOrigin), path.StartsWith('/') ? path : $"/{path}");
    }

    private async Task<ApiResult<JsonElement>> SendJsonAsync(HttpMethod method, string path, object? body, CancellationToken cancellationToken)
    {
        try
        {
            using var request = new HttpRequestMessage(method, NormalizePath(path));
            if (body is not null) request.Content = JsonContent.Create(body);
            using var response = await _httpClient.SendAsync(request, cancellationToken);
            return await ParseResponseAsync(response, cancellationToken);
        }
        catch (Exception error) when (error is HttpRequestException or TaskCanceledException or JsonException)
        {
            return ApiResult<JsonElement>.Failure("NETWORK_ERROR", error is TaskCanceledException ? "连接短剧生产站超时" : $"连接短剧生产站失败：{error.Message}");
        }
    }

    private static async Task<ApiResult<JsonElement>> ParseResponseAsync(HttpResponseMessage response, CancellationToken cancellationToken)
    {
        var body = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            return ApiResult<JsonElement>.Failure(
                response.StatusCode == HttpStatusCode.Unauthorized ? "UNAUTHORIZED" : $"HTTP_{(int)response.StatusCode}",
                ReadError(body, response.ReasonPhrase ?? "请求失败"));
        }

        if (string.IsNullOrWhiteSpace(body)) return ApiResult<JsonElement>.Success(JsonSerializer.SerializeToElement(new { }));
        using var document = JsonDocument.Parse(body);
        var root = document.RootElement;
        if (root.ValueKind == JsonValueKind.Object && root.TryGetProperty("ok", out var ok) && ok.ValueKind == JsonValueKind.False)
        {
            return ApiResult<JsonElement>.Failure(ReadCode(root), ReadError(body, "请求失败"));
        }
        if (root.ValueKind == JsonValueKind.Object && root.TryGetProperty("data", out var data))
        {
            return ApiResult<JsonElement>.Success(data.Clone());
        }
        return ApiResult<JsonElement>.Success(root.Clone());
    }

    private static string NormalizePath(string path)
    {
        if (Uri.TryCreate(path, UriKind.Absolute, out var absolute)) return absolute.PathAndQuery;
        var normalized = path.StartsWith('/') ? path : $"/{path}";
        return normalized.StartsWith("/api/", StringComparison.OrdinalIgnoreCase) ? normalized : $"/api/v1{normalized}";
    }

    private static string ReadCode(JsonElement root)
    {
        if (root.TryGetProperty("code", out var code) && code.ValueKind == JsonValueKind.String) return code.GetString() ?? "API_ERROR";
        return "API_ERROR";
    }

    private static string ReadError(string body, string fallback)
    {
        try
        {
            using var document = JsonDocument.Parse(body);
            var root = document.RootElement;
            foreach (var name in new[] { "error", "message", "detail" })
            {
                if (!root.TryGetProperty(name, out var value)) continue;
                if (value.ValueKind == JsonValueKind.String) return value.GetString() ?? fallback;
                if (value.ValueKind == JsonValueKind.Object && value.TryGetProperty("message", out var nested) && nested.ValueKind == JsonValueKind.String) return nested.GetString() ?? fallback;
            }
        }
        catch (JsonException) { }
        return string.IsNullOrWhiteSpace(body) ? fallback : body.Length > 360 ? body[..360] : body;
    }

    public void Dispose() => _httpClient.Dispose();
}
