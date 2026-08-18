using System.Text.Json.Serialization;

namespace Gulong.ShortDrama.Core;

public static class TaskContracts
{
    private static readonly HashSet<string> AllowedAspectRatios = ["9:16", "16:9", "1:1", "4:3", "3:4"];

    public static H3TaskRequest Build(string? prompt, int durationSeconds, string? aspectRatio)
    {
        var normalizedPrompt = (prompt ?? string.Empty).Trim();
        if (normalizedPrompt.Length is < 1 or > 20_000)
        {
            throw new ContractValidationException("提示词需为 1–20000 个字符");
        }

        if (durationSeconds is < 1 or > 600)
        {
            throw new ContractValidationException("视频时长需为 1–600 秒");
        }

        var normalizedRatio = AllowedAspectRatios.Contains(aspectRatio ?? string.Empty) ? aspectRatio! : "9:16";
        return new H3TaskRequest(normalizedPrompt, normalizedRatio, durationSeconds);
    }

    public static string CreateIdempotencyKey() => $"dramaclaw-native-{DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()}-{Guid.NewGuid():N}";
}

public sealed class ContractValidationException(string message) : Exception(message);

public sealed record H3TaskRequest(
    [property: JsonPropertyName("prompt")] string Prompt,
    [property: JsonPropertyName("aspect_ratio")] string AspectRatio,
    [property: JsonPropertyName("duration_seconds")] int DurationSeconds)
{
    [JsonPropertyName("source_channel")]
    public string SourceChannel => "desktop_agent";

    [JsonPropertyName("model")]
    public string Model => "minimax_h3_shared";

    [JsonPropertyName("profile")]
    public string Profile => "balanced";

    [JsonPropertyName("assets")]
    public H3Assets Assets { get; } = new();
}

public sealed record H3Assets
{
    [JsonPropertyName("images")]
    public IReadOnlyList<string> Images { get; } = [];

    [JsonPropertyName("videos")]
    public IReadOnlyList<string> Videos { get; } = [];

    [JsonPropertyName("audio")]
    public IReadOnlyList<string> Audio { get; } = [];
}
