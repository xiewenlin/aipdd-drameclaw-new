namespace Gulong.ShortDrama.Models;

public sealed record UserAccount(
    string DisplayName,
    string? Username,
    string? Email,
    long BalanceFen,
    bool IsMember,
    string? SubscriptionStatus);

public sealed record VideoTask(
    string Id,
    string OrderNo,
    string Prompt,
    string Status,
    string AspectRatio,
    int DurationSeconds,
    long PriceFen,
    DateTimeOffset? CreatedAt)
{
    public string StatusText => Status switch
    {
        "queued" => "排队中",
        "claimed" or "processing" => "生成中",
        "completed" => "已完成",
        "failed" => "失败",
        "cancelled" => "已取消",
        "rejected" => "未扣费",
        _ => string.IsNullOrWhiteSpace(Status) ? "未知" : Status,
    };

    public string PriceText => $"¥{PriceFen / 100.0:F2}";
    public string CreatedAtText => CreatedAt?.ToLocalTime().ToString("yyyy-MM-dd HH:mm") ?? "—";
}

public sealed record TaskCreationResult(VideoTask Task, long ChargedFen, long RemainingBalanceFen);

public sealed record ApiResult<T>(bool IsSuccess, T? Value, string Code, string Message)
{
    public static ApiResult<T> Success(T value) => new(true, value, string.Empty, string.Empty);
    public static ApiResult<T> Failure(string code, string message) => new(false, default, code, message);
}
