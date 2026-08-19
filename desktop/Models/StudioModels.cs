namespace Gulong.ShortDrama.Models;

public sealed record ProjectRow(string Id, string DisplayName, string Status, int EpisodeCount, int BeatCount, DateTimeOffset? UpdatedAt)
{
    public string StatusText => Status switch { "active" => "进行中", "archived" => "已归档", "deleted" => "回收站", _ => Status };
    public string UpdatedText => UpdatedAt?.ToLocalTime().ToString("yyyy-MM-dd HH:mm") ?? "—";
}

public sealed record ChapterRow(int Number, string Title, string Preview, int CharacterCount);
public sealed record StyleRow(string Id, string Name, string Description, string PreviewUrl);
public sealed record CharacterRow(string Name, string Role, string Gender, bool IsMain, string Description, string FacePrompt, string PortraitUrl);
public sealed record SceneRow(string Name, string Type, string TimeOfDay, string Description, string MasterUrl);
public sealed record PropRow(string Name, string Description, string ReferenceUrl);
public sealed record EpisodeRow(int Number, string Title, string Summary, string Status);
public sealed record BeatRow(int Number, string Visual, string Narration, string Speaker, string FrameUrl, string VideoUrl, string AudioUrl)
{
    public string AssetStatus => !string.IsNullOrWhiteSpace(VideoUrl) ? "视频完成" : !string.IsNullOrWhiteSpace(FrameUrl) ? "分镜完成" : "待制作";
}

public sealed record VoiceRow(string Id, string Name, string Language, string Description);
public sealed record VideoCandidateRow(int Beat, string Id, string Status, string Url);
public sealed record AssetRow(string Id, string Category, string Kind, string Label, string MediaType, bool Exists, string Url);
public sealed record CanvasRow(string Id, string Name, DateTimeOffset? UpdatedAt)
{
    public string UpdatedText => UpdatedAt?.ToLocalTime().ToString("MM-dd HH:mm") ?? "—";
}

public sealed record SkillRow(string Id, string Name, string Description, string InputRole);

public sealed record ProductionTaskRow(
    string Type,
    string Status,
    int Episode,
    int? Beat,
    string Scope,
    double Progress,
    string CurrentTask,
    string Error,
    DateTimeOffset? UpdatedAt)
{
    public string StatusText => Status switch
    {
        "submitting" => "提交中", "queued" or "pending" or "starting" => "排队中", "running" => "执行中",
        "completed" => "已完成", "failed" => "失败", "cancelled" => "已取消", _ => Status,
    };
    public string ScopeText => $"第{Episode}集" + (Beat.HasValue ? $" / 镜头{Beat}" : string.Empty) + (string.IsNullOrWhiteSpace(Scope) ? string.Empty : $" / {Scope}");
    public string ProgressText => $"{Math.Clamp(Progress <= 1 ? Progress * 100 : Progress, 0, 100):0}%";
    public string UpdatedText => UpdatedAt?.ToLocalTime().ToString("MM-dd HH:mm:ss") ?? "—";
}
