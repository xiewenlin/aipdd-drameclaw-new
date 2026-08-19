using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using Gulong.ShortDrama.Models;
using Gulong.ShortDrama.Services;
using Microsoft.Win32;

namespace Gulong.ShortDrama;

public partial class ProductionWorkspace : UserControl
{
    private static readonly JsonSerializerOptions PrettyJson = new() { WriteIndented = true };
    private readonly DramaApiClient _api;
    private readonly Func<Task<bool>> _ensureAuthenticated;
    private readonly ObservableCollection<ProjectRow> _projects = [];
    private readonly ObservableCollection<ChapterRow> _chapters = [];
    private readonly ObservableCollection<StyleRow> _styles = [];
    private readonly ObservableCollection<CharacterRow> _characters = [];
    private readonly ObservableCollection<SceneRow> _scenes = [];
    private readonly ObservableCollection<PropRow> _props = [];
    private readonly ObservableCollection<EpisodeRow> _episodes = [];
    private readonly ObservableCollection<BeatRow> _beats = [];
    private readonly ObservableCollection<VoiceRow> _voices = [];
    private readonly ObservableCollection<VideoCandidateRow> _videoPool = [];
    private readonly ObservableCollection<AssetRow> _assets = [];
    private readonly ObservableCollection<AssetRow> _filteredAssets = [];
    private readonly ObservableCollection<CanvasRow> _canvases = [];
    private readonly ObservableCollection<SkillRow> _skills = [];
    private readonly ObservableCollection<ProductionTaskRow> _productionTasks = [];
    private string? _uploadedFilename;
    private bool _sessionReady;
    private bool _projectSelectionChanging;
    private JsonElement? _lastRenderPlan;

    public ProductionWorkspace(DramaApiClient api, Func<Task<bool>> ensureAuthenticated)
    {
        _api = api;
        _ensureAuthenticated = ensureAuthenticated;
        InitializeComponent();
        ProjectsGrid.ItemsSource = _projects;
        ProjectComboBox.ItemsSource = _projects;
        ChaptersGrid.ItemsSource = _chapters;
        StylesGrid.ItemsSource = _styles;
        CharactersGrid.ItemsSource = _characters;
        ScenesGrid.ItemsSource = _scenes;
        PropsGrid.ItemsSource = _props;
        EpisodesGrid.ItemsSource = _episodes;
        BeatsGrid.ItemsSource = _beats;
        VoicesGrid.ItemsSource = _voices;
        VideoPoolGrid.ItemsSource = _videoPool;
        AssetsGrid.ItemsSource = _filteredAssets;
        CanvasesGrid.ItemsSource = _canvases;
        SkillComboBox.ItemsSource = _skills;
        ProductionTasksGrid.ItemsSource = _productionTasks;
    }

    public async Task InitializeAsync()
    {
        if (!await EnsureSessionAsync()) return;
        await LoadProjectsAsync();
    }

    private string? CurrentProjectId => ProjectComboBox.SelectedValue?.ToString();
    private int CurrentEpisode => (EpisodesGrid.SelectedItem as EpisodeRow)?.Number ?? _episodes.FirstOrDefault()?.Number ?? 0;

    private async Task<bool> EnsureSessionAsync()
    {
        if (_sessionReady) return true;
        SetBusy(true, "正在连接古龙短剧生产空间…");
        try
        {
            _sessionReady = await _ensureAuthenticated();
            ProductionStatusText.Text = _sessionReady ? "古龙账号已连接" : "需要登录古龙账号";
            return _sessionReady;
        }
        finally { SetBusy(false); }
    }

    private async Task<JsonElement?> RequestAsync(string busyText, Func<Task<ApiResult<JsonElement>>> action, string? successText = null, bool showError = true)
    {
        if (!await EnsureSessionAsync()) return null;
        SetBusy(true, busyText);
        try
        {
            var result = await action();
            if (!result.IsSuccess && result.Code == "UNAUTHORIZED")
            {
                _sessionReady = false;
                if (!await EnsureSessionAsync()) return null;
                result = await action();
            }
            if (!result.IsSuccess)
            {
                ProductionStatusText.Text = result.Message;
                if (showError) MessageBox.Show(Window.GetWindow(this), result.Message, "短剧生产工作台", MessageBoxButton.OK, MessageBoxImage.Warning);
                return null;
            }
            ProductionStatusText.Text = successText ?? "操作完成";
            return result.Value;
        }
        catch (Exception error)
        {
            ProductionStatusText.Text = error.Message;
            if (showError) MessageBox.Show(Window.GetWindow(this), error.Message, "短剧生产工作台", MessageBoxButton.OK, MessageBoxImage.Error);
            return null;
        }
        finally { SetBusy(false); }
    }

    private void SetBusy(bool busy, string text = "正在处理…")
    {
        BusyText.Text = text;
        BusyOverlay.Visibility = busy ? Visibility.Visible : Visibility.Collapsed;
    }

    private bool RequireProject(out string project)
    {
        project = CurrentProjectId ?? string.Empty;
        if (!string.IsNullOrWhiteSpace(project)) return true;
        MessageBox.Show(Window.GetWindow(this), "请先在顶部选择一个项目", "短剧生产工作台", MessageBoxButton.OK, MessageBoxImage.Information);
        return false;
    }

    private bool RequireEpisode(out string project, out int episode)
    {
        episode = CurrentEpisode;
        if (!RequireProject(out project)) return false;
        if (episode > 0) return true;
        MessageBox.Show(Window.GetWindow(this), "请先在“分集规划”中选择一个分集", "短剧生产工作台", MessageBoxButton.OK, MessageBoxImage.Information);
        return false;
    }

    private static string E(string value) => Uri.EscapeDataString(value);

    private async Task LoadProjectsAsync()
    {
        var data = await RequestAsync("正在读取项目…", () => _api.GetAsync("/api/v1/projects/summaries?status=all"), "项目已刷新");
        if (!data.HasValue) return;
        var selected = CurrentProjectId;
        _projects.Clear();
        foreach (var item in ArrayOf(data.Value, "projects", "items"))
        {
            if (item.ValueKind == JsonValueKind.String)
            {
                var name = item.GetString() ?? string.Empty;
                _projects.Add(new ProjectRow(name, name, "active", 0, 0, null));
                continue;
            }
            var id = Text(item, "id", "project_id", "name");
            if (string.IsNullOrWhiteSpace(id)) continue;
            _projects.Add(new ProjectRow(id, Text(item, "display_name", "name") ?? id, Text(item, "status") ?? "active", Number(item, "episode_count"), Number(item, "beat_count"), Date(item, "updated_at")));
        }
        if (_projects.Count == 0)
        {
            var fallback = await RequestAsync("正在读取项目…", () => _api.GetAsync("/api/v1/projects"), showError: false);
            if (fallback.HasValue)
            {
                foreach (var item in ArrayOf(fallback.Value))
                {
                    var name = item.ValueKind == JsonValueKind.String ? item.GetString() : Text(item, "id", "name");
                    if (!string.IsNullOrWhiteSpace(name)) _projects.Add(new ProjectRow(name, name, "active", 0, 0, null));
                }
            }
        }
        _projectSelectionChanging = true;
        ProjectComboBox.SelectedItem = _projects.FirstOrDefault(p => p.Id == selected) ?? _projects.FirstOrDefault(p => p.Status == "active") ?? _projects.FirstOrDefault();
        ProjectsGrid.SelectedItem = ProjectComboBox.SelectedItem;
        _projectSelectionChanging = false;
    }

    private async void StageList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (StudioTabs is null || StageList.SelectedIndex < 0) return;
        StudioTabs.SelectedIndex = StageList.SelectedIndex;
        await LoadStageAsync(StageList.SelectedIndex);
    }

    private async Task LoadStageAsync(int index)
    {
        if (index > 0 && !RequireProject(out _)) return;
        switch (index)
        {
            case 0: await LoadProjectsAsync(); break;
            case 1: await LoadChaptersAsync(); break;
            case 2: await LoadStylesAsync(); break;
            case 3: await LoadCharactersAsync(); break;
            case 4: await Task.WhenAll(LoadScenesAsync(), LoadPropsAsync()); break;
            case 5: await LoadEpisodesAsync(); break;
            case 6: await LoadScriptAsync(); break;
            case 7: await LoadBeatsAsync(); break;
            case 8: await LoadVoicesAsync(); break;
            case 9: await Task.WhenAll(LoadVideoBackendsAsync(), LoadVideoPoolAsync()); break;
            case 10: await LoadFinalAsync(); break;
            case 11: await LoadAssetsAsync(); break;
            case 12: await LoadCanvasesAsync(); break;
            case 13: await LoadSkillsAsync(); break;
            case 14: await LoadProductionTasksAsync(); break;
        }
    }

    private async void ProjectComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_projectSelectionChanging || CurrentProjectId is null) return;
        ProjectsGrid.SelectedItem = ProjectComboBox.SelectedItem;
        ProductionStatusText.Text = $"当前项目：{(ProjectComboBox.SelectedItem as ProjectRow)?.DisplayName}";
        ClearProjectData();
        await LoadStageAsync(StageList.SelectedIndex);
    }

    private void ProjectsGrid_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (ProjectsGrid.SelectedItem is ProjectRow project && !Equals(ProjectComboBox.SelectedItem, project)) ProjectComboBox.SelectedItem = project;
    }

    private void ClearProjectData()
    {
        _chapters.Clear(); _styles.Clear(); _characters.Clear(); _scenes.Clear(); _props.Clear(); _episodes.Clear(); _beats.Clear();
        _voices.Clear(); _videoPool.Clear(); _assets.Clear(); _filteredAssets.Clear(); _canvases.Clear(); _skills.Clear(); _productionTasks.Clear();
        ScriptEditorTextBox.Clear(); FinalResultTextBox.Clear(); SkillResultTextBox.Clear();
    }

    private void NewProjectButton_Click(object sender, RoutedEventArgs e) { StageList.SelectedIndex = 0; ProjectNameTextBox.Focus(); }
    private async void RefreshProjectsButton_Click(object sender, RoutedEventArgs e) => await LoadProjectsAsync();

    private async void CreateProjectButton_Click(object sender, RoutedEventArgs e)
    {
        var name = ProjectNameTextBox.Text.Trim();
        if (name.Length < 2) { MessageBox.Show("项目名称至少需要 2 个字符"); return; }
        var data = await RequestAsync("正在创建项目…", () => _api.PostAsync("/api/v1/projects", new { name }), "项目已创建");
        if (!data.HasValue) return;
        ProjectNameTextBox.Clear();
        await LoadProjectsAsync();
        var id = Text(data.Value, "id", "project_id", "name");
        ProjectComboBox.SelectedItem = _projects.FirstOrDefault(p => p.Id == id || p.DisplayName == name);
    }

    private async Task ChangeProjectStateAsync(string action, string label)
    {
        if (ProjectsGrid.SelectedItem is not ProjectRow project) return;
        var data = await RequestAsync($"正在{label}…", () => _api.PostAsync($"/api/v1/projects/{E(project.Id)}/{action}"), $"项目已{label}");
        if (data.HasValue) await LoadProjectsAsync();
    }
    private async void ArchiveProjectButton_Click(object sender, RoutedEventArgs e) => await ChangeProjectStateAsync("archive", "归档");
    private async void RestoreProjectButton_Click(object sender, RoutedEventArgs e) => await ChangeProjectStateAsync("restore", "恢复");
    private async void DeleteProjectButton_Click(object sender, RoutedEventArgs e) => await ChangeProjectStateAsync("delete", "移入回收站");

    private void ChooseIngestFileButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog { Title = "选择小说或剧本", Filter = "文本与剧本|*.txt;*.md;*.markdown;*.json;*.fountain|所有文件|*.*" };
        if (dialog.ShowDialog(Window.GetWindow(this)) == true) IngestFileTextBox.Text = dialog.FileName;
    }

    private async void UploadIngestButton_Click(object sender, RoutedEventArgs e)
    {
        if (!RequireProject(out var project) || !File.Exists(IngestFileTextBox.Text)) { MessageBox.Show("请先选择要导入的文件"); return; }
        var upload = await RequestAsync("正在上传并解析文本…", () => _api.UploadFileAsync($"/api/v1/projects/{E(project)}/ingest/upload", IngestFileTextBox.Text), "文本解析完成");
        if (!upload.HasValue) return;
        _uploadedFilename = Text(upload.Value, "filename") ?? Path.GetFileName(IngestFileTextBox.Text);
        FillChapters(upload.Value);
        var start = await RequestAsync("正在构建故事知识图谱…", () => _api.PostAsync($"/api/v1/projects/{E(project)}/ingest/start", new { filename = _uploadedFilename, rebuild = false }), "导入任务已提交");
        if (start.HasValue) await LoadProductionTasksAsync();
    }

    private async void RebuildGraphButton_Click(object sender, RoutedEventArgs e)
    {
        if (!RequireProject(out var project)) return;
        var data = await RequestAsync("正在提交知识图谱重建…", () => _api.PostAsync($"/api/v1/projects/{E(project)}/ingest/rebuild"), "知识图谱重建任务已提交");
        if (data.HasValue) await LoadProductionTasksAsync();
    }

    private async Task LoadChaptersAsync()
    {
        if (!RequireProject(out var project)) return;
        var data = await RequestAsync("正在读取章节…", () => _api.GetAsync($"/api/v1/projects/{E(project)}/chapters"), "章节已读取", false);
        if (data.HasValue) FillChapters(data.Value);
    }

    private void FillChapters(JsonElement data)
    {
        _chapters.Clear();
        var n = 0;
        foreach (var item in ArrayOf(data, "chapters", "items"))
        {
            n++;
            var content = Text(item, "content", "text", "body", "summary") ?? string.Empty;
            _chapters.Add(new ChapterRow(Number(item, "number", "chapter_num", "index") is var value && value > 0 ? value : n, Text(item, "title", "name") ?? $"第 {n} 章", content.Length > 180 ? content[..180] + "…" : content, Number(item, "character_count", "char_count", "length") is var count && count > 0 ? count : content.Length));
        }
    }

    private async Task LoadStylesAsync()
    {
        if (!RequireProject(out var project)) return;
        var data = await RequestAsync("正在读取视觉风格…", () => _api.GetAsync($"/api/v1/styles?project={E(project)}"), "视觉风格已刷新", false);
        if (!data.HasValue) return;
        _styles.Clear();
        foreach (var item in ArrayOf(data.Value, "styles", "items")) _styles.Add(new StyleRow(Text(item, "id", "style_id") ?? string.Empty, Text(item, "name", "display_name") ?? Text(item, "id") ?? "未命名", Text(item, "description", "prompt") ?? string.Empty, Text(item, "preview_url", "preview_path") ?? string.Empty));
    }
    private async void RefreshStylesButton_Click(object sender, RoutedEventArgs e) => await LoadStylesAsync();
    private void StylesGrid_SelectionChanged(object sender, SelectionChangedEventArgs e) { if (StylesGrid.SelectedItem is StyleRow row) { StyleIdTextBox.Text = row.Id; StyleNameTextBox.Text = row.Name; StyleConfigTextBox.Text = row.Description; } }

    private async void CreateStyleButton_Click(object sender, RoutedEventArgs e)
    {
        if (!RequireProject(out var project)) return;
        var id = StyleIdTextBox.Text.Trim(); var name = StyleNameTextBox.Text.Trim();
        if (id.Length == 0 || name.Length == 0) { MessageBox.Show("请填写风格 ID 和名称"); return; }
        var config = JsonOrPrompt(StyleConfigTextBox.Text);
        var data = await RequestAsync("正在创建视觉风格…", () => _api.PostAsync("/api/v1/styles", new { id, name, project, config }), "视觉风格已创建");
        if (data.HasValue) await LoadStylesAsync();
    }
    private async void SetDefaultStyleButton_Click(object sender, RoutedEventArgs e)
    {
        if (!RequireProject(out var project) || StylesGrid.SelectedItem is not StyleRow style) return;
        await RequestAsync("正在应用视觉风格…", () => _api.PatchAsync($"/api/v1/projects/{E(project)}", new { visual_style = style.Id }), "项目默认风格已更新");
    }
    private async void AnalyzeStyleButton_Click(object sender, RoutedEventArgs e)
    {
        if (!RequireProject(out var project)) return;
        var file = PickFile("选择风格参考图", "图片|*.png;*.jpg;*.jpeg;*.webp"); if (file is null) return;
        var data = await RequestAsync("正在分析参考图…", () => _api.UploadFileAsync($"/api/v1/projects/{E(project)}/styles/analyze", file), "风格分析完成");
        if (data.HasValue) StyleConfigTextBox.Text = Format(data.Value);
    }
    private async void DeleteStyleButton_Click(object sender, RoutedEventArgs e)
    {
        if (!RequireProject(out var project) || StylesGrid.SelectedItem is not StyleRow style) return;
        var data = await RequestAsync("正在删除视觉风格…", () => _api.DeleteAsync($"/api/v1/styles/{E(style.Id)}?project={E(project)}"), "视觉风格已删除");
        if (data.HasValue) await LoadStylesAsync();
    }

    private async Task LoadCharactersAsync()
    {
        if (!RequireProject(out var project)) return;
        var data = await RequestAsync("正在读取角色…", () => _api.GetAsync($"/api/v1/projects/{E(project)}/characters"), "角色已刷新", false);
        if (!data.HasValue) return;
        _characters.Clear();
        foreach (var item in ArrayOf(data.Value, "characters", "items")) _characters.Add(new CharacterRow(Text(item, "name", "display_name") ?? "未命名", Text(item, "role") ?? string.Empty, Text(item, "gender") ?? string.Empty, Boolean(item, "is_main"), Text(item, "description") ?? string.Empty, Text(item, "face_prompt") ?? string.Empty, Text(item, "portrait_url") ?? string.Empty));
    }
    private void CharactersGrid_SelectionChanged(object sender, SelectionChangedEventArgs e) { if (CharactersGrid.SelectedItem is CharacterRow row) { CharacterNameTextBox.Text = row.Name; CharacterRoleTextBox.Text = row.Role; CharacterGenderTextBox.Text = row.Gender; CharacterMainCheckBox.IsChecked = row.IsMain; CharacterDescriptionTextBox.Text = row.Description; CharacterFacePromptTextBox.Text = row.FacePrompt; } }
    private async void BuildCharactersButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p)) return; var d = await RequestAsync("正在构建角色…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/characters/build"), "角色构建任务已提交"); if (d.HasValue) await LoadProductionTasksAsync(); }
    private object CharacterPayload() => new { name = CharacterNameTextBox.Text.Trim(), role = CharacterRoleTextBox.Text.Trim(), gender = CharacterGenderTextBox.Text.Trim(), is_main = CharacterMainCheckBox.IsChecked == true, description = CharacterDescriptionTextBox.Text.Trim(), face_prompt = CharacterFacePromptTextBox.Text.Trim() };
    private async void CreateCharacterButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p) || CharacterNameTextBox.Text.Trim().Length == 0) return; var d = await RequestAsync("正在新增角色…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/characters", CharacterPayload()), "角色已新增"); if (d.HasValue) await LoadCharactersAsync(); }
    private async void UpdateCharacterButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p) || CharactersGrid.SelectedItem is not CharacterRow row) return; var d = await RequestAsync("正在保存角色…", () => _api.PatchAsync($"/api/v1/projects/{E(p)}/characters/{E(row.Name)}", CharacterPayload()), "角色已保存"); if (d.HasValue) await LoadCharactersAsync(); }
    private async void DeleteCharacterButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p) || CharactersGrid.SelectedItem is not CharacterRow row) return; var d = await RequestAsync("正在删除角色…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/characters/{E(row.Name)}/delete"), "角色已删除"); if (d.HasValue) await LoadCharactersAsync(); }
    private async void GeneratePortraitButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p) || CharactersGrid.SelectedItem is not CharacterRow row) return; var d = await RequestAsync("正在提交肖像生成…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/characters/{E(row.Name)}/portrait-async"), "肖像生成任务已提交"); if (d.HasValue) await LoadProductionTasksAsync(); }
    private async void UploadPortraitButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p) || CharactersGrid.SelectedItem is not CharacterRow row) return; var file = PickFile("上传角色肖像", "图片|*.png;*.jpg;*.jpeg;*.webp"); if (file is null) return; var d = await RequestAsync("正在上传肖像…", () => _api.UploadFileAsync($"/api/v1/projects/{E(p)}/characters/{E(row.Name)}/portrait/upload", file), "角色肖像已更新"); if (d.HasValue) await LoadCharactersAsync(); }

    private async Task LoadScenesAsync()
    {
        if (!RequireProject(out var p)) return; var data = await RequestAsync("正在读取场景…", () => _api.GetAsync($"/api/v1/projects/{E(p)}/scenes"), "场景已刷新", false); if (!data.HasValue) return;
        _scenes.Clear(); foreach (var item in ArrayOf(data.Value, "scenes", "items")) _scenes.Add(new SceneRow(Text(item, "name", "scene_id") ?? "未命名", Text(item, "scene_type", "type") ?? string.Empty, Text(item, "time_of_day") ?? string.Empty, Text(item, "description", "environment_prompt") ?? string.Empty, Text(item, "master_url", "image_url") ?? string.Empty));
    }
    private void ScenesGrid_SelectionChanged(object sender, SelectionChangedEventArgs e) { if (ScenesGrid.SelectedItem is SceneRow row) { SceneNameTextBox.Text = row.Name; SceneTypeTextBox.Text = row.Type; SceneTimeTextBox.Text = row.TimeOfDay; SceneDescriptionTextBox.Text = row.Description; } }
    private async void CreateSceneButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p) || SceneNameTextBox.Text.Trim().Length == 0) return; var d = await RequestAsync("正在新增场景…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/scenes", new { name = SceneNameTextBox.Text.Trim(), scene_type = SceneTypeTextBox.Text.Trim(), time_of_day = SceneTimeTextBox.Text.Trim(), description = SceneDescriptionTextBox.Text.Trim(), environment_prompt = SceneDescriptionTextBox.Text.Trim() }), "场景已新增"); if (d.HasValue) await LoadScenesAsync(); }
    private async void DeleteSceneButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p) || ScenesGrid.SelectedItem is not SceneRow row) return; var d = await RequestAsync("正在删除场景…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/scenes/{E(row.Name)}/delete"), "场景已删除"); if (d.HasValue) await LoadScenesAsync(); }
    private async void GenerateSceneMasterButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p) || ScenesGrid.SelectedItem is not SceneRow row) return; var d = await RequestAsync("正在提交场景母版生成…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/scenes/{E(row.Name)}/master/generate-async"), "场景母版任务已提交"); if (d.HasValue) await LoadProductionTasksAsync(); }
    private async void GenerateScenePanoButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p) || ScenesGrid.SelectedItem is not SceneRow row) return; var d = await RequestAsync("正在提交全景背景生成…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/scenes/{E(row.Name)}/pano/generate-async", new { source = "master" }), "全景背景任务已提交"); if (d.HasValue) await LoadProductionTasksAsync(); }
    private async void UploadSceneMasterButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p) || ScenesGrid.SelectedItem is not SceneRow row) return; var file = PickFile("上传场景母版", "图片|*.png;*.jpg;*.jpeg;*.webp"); if (file is null) return; var d = await RequestAsync("正在上传场景母版…", () => _api.UploadFileAsync($"/api/v1/projects/{E(p)}/scenes/{E(row.Name)}/master/upload", file), "场景母版已更新"); if (d.HasValue) await LoadScenesAsync(); }

    private async Task LoadPropsAsync()
    {
        if (!RequireProject(out var p)) return; var data = await RequestAsync("正在读取道具…", () => _api.GetAsync($"/api/v1/projects/{E(p)}/props"), "道具已刷新", false); if (!data.HasValue) return;
        _props.Clear(); foreach (var item in ArrayOf(data.Value, "props", "items")) _props.Add(new PropRow(Text(item, "name", "prop_id") ?? "未命名", Text(item, "description", "prompt") ?? string.Empty, Text(item, "reference_url", "image_url") ?? string.Empty));
    }
    private void PropsGrid_SelectionChanged(object sender, SelectionChangedEventArgs e) { if (PropsGrid.SelectedItem is PropRow row) { PropNameTextBox.Text = row.Name; PropDescriptionTextBox.Text = row.Description; } }
    private async void CreatePropButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p) || PropNameTextBox.Text.Trim().Length == 0) return; var d = await RequestAsync("正在新增道具…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/props", new { name = PropNameTextBox.Text.Trim(), description = PropDescriptionTextBox.Text.Trim() }), "道具已新增"); if (d.HasValue) await LoadPropsAsync(); }
    private async void DeletePropButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p) || PropsGrid.SelectedItem is not PropRow row) return; var d = await RequestAsync("正在删除道具…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/props/{E(row.Name)}/delete"), "道具已删除"); if (d.HasValue) await LoadPropsAsync(); }
    private async void GeneratePropButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p) || PropsGrid.SelectedItem is not PropRow row) return; var d = await RequestAsync("正在提交道具参考图生成…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/props/{E(row.Name)}/reference/generate-async"), "道具参考图任务已提交"); if (d.HasValue) await LoadProductionTasksAsync(); }
    private async void BatchGeneratePropsButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p)) return; var d = await RequestAsync("正在提交道具批量生成…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/props/reference/batch-generate"), "道具批量生成任务已提交"); if (d.HasValue) await LoadProductionTasksAsync(); }

    private async Task LoadEpisodesAsync()
    {
        if (!RequireProject(out var p)) return; var selected = CurrentEpisode; var data = await RequestAsync("正在读取分集…", () => _api.GetAsync($"/api/v1/projects/{E(p)}/episodes"), "分集已刷新", false); if (!data.HasValue) return;
        _episodes.Clear(); foreach (var item in ArrayOf(data.Value, "episodes", "items")) { var num = Number(item, "number", "episode_num", "episode"); if (num > 0) _episodes.Add(new EpisodeRow(num, Text(item, "title", "name") ?? $"第 {num} 集", Text(item, "summary", "synopsis", "description") ?? string.Empty, Text(item, "status") ?? "")); }
        EpisodesGrid.SelectedItem = _episodes.FirstOrDefault(x => x.Number == selected) ?? _episodes.FirstOrDefault();
        UpdateEpisodeCaption();
    }
    private void EpisodesGrid_SelectionChanged(object sender, SelectionChangedEventArgs e) => UpdateEpisodeCaption();
    private void UpdateEpisodeCaption() => ScriptEpisodeText.Text = CurrentEpisode > 0 ? $"当前编辑：第 {CurrentEpisode} 集" : "请选择分集";
    private async void RefreshEpisodesButton_Click(object sender, RoutedEventArgs e) => await LoadEpisodesAsync();
    private async void BuildEpisodesButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p)) return; var target = int.TryParse(TargetEpisodesTextBox.Text, out var n) ? Math.Clamp(n, 1, 200) : 8; var mode = (PlanningModeComboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "standard"; var d = await RequestAsync("正在提交分集规划…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/episodes/plan", new { target_episodes = target, planning_mode = mode }), "分集规划任务已提交"); if (d.HasValue) await LoadProductionTasksAsync(); }

    private async Task LoadScriptAsync()
    {
        if (!RequireEpisode(out var p, out var ep)) return; var data = await RequestAsync("正在读取剧本…", () => _api.GetAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/script"), "剧本已读取", false); if (data.HasValue) ScriptEditorTextBox.Text = Format(data.Value);
    }
    private async void LoadScriptButton_Click(object sender, RoutedEventArgs e) => await LoadScriptAsync();
    private async void GenerateScriptButton_Click(object sender, RoutedEventArgs e) { if (!RequireEpisode(out var p, out var ep)) return; var d = await RequestAsync("正在提交剧本生成…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/script/generate"), "剧本生成任务已提交"); if (d.HasValue) await LoadProductionTasksAsync(); }
    private void FormatScriptButton_Click(object sender, RoutedEventArgs e) { try { using var doc = JsonDocument.Parse(ScriptEditorTextBox.Text); ScriptEditorTextBox.Text = Format(doc.RootElement); } catch (JsonException error) { MessageBox.Show($"JSON 格式错误：{error.Message}"); } }
    private async void SaveScriptButton_Click(object sender, RoutedEventArgs e) { if (!RequireEpisode(out var p, out var ep)) return; var body = ParseJson(ScriptEditorTextBox.Text); if (body is null) { MessageBox.Show("请先修正剧本 JSON 格式"); return; } await RequestAsync("正在保存剧本…", () => _api.PutAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/script", body), "剧本已保存"); }

    private async Task LoadBeatsAsync()
    {
        if (!RequireEpisode(out var p, out var ep)) return; var data = await RequestAsync("正在读取镜头节拍…", () => _api.GetAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/beats"), "镜头节拍已读取", false); if (!data.HasValue) return;
        _beats.Clear(); foreach (var item in ArrayOf(data.Value, "beats", "items")) { var num = Number(item, "beat_number", "beat_num", "beat_index", "number"); if (num <= 0) num = _beats.Count + 1; _beats.Add(new BeatRow(num, Text(item, "visual_description", "visual") ?? string.Empty, Text(item, "narration_segment", "dialogue", "narration") ?? string.Empty, Text(item, "speaker") ?? string.Empty, Text(item, "frame_url", "sketch_url") ?? string.Empty, Text(item, "video_url") ?? string.Empty, Text(item, "audio_url") ?? string.Empty)); }
    }
    private void BeatsGrid_SelectionChanged(object sender, SelectionChangedEventArgs e) { if (BeatsGrid.SelectedItem is BeatRow row) { BeatNumberTextBox.Text = row.Number.ToString(); BeatVisualTextBox.Text = row.Visual; BeatNarrationTextBox.Text = row.Narration; VideoBeatNumberTextBox.Text = row.Number.ToString(); AudioBeatNumberTextBox.Text = row.Number.ToString(); } }
    private async void LoadBeatsButton_Click(object sender, RoutedEventArgs e) => await LoadBeatsAsync();
    private async void UpdateBeatButton_Click(object sender, RoutedEventArgs e) { if (!RequireEpisode(out var p, out var ep) || !int.TryParse(BeatNumberTextBox.Text, out var beat)) return; var d = await RequestAsync("正在保存镜头…", () => _api.PatchAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/beats/{beat}", new { visual_description = BeatVisualTextBox.Text.Trim(), narration_segment = BeatNarrationTextBox.Text.Trim() }), "镜头已保存"); if (d.HasValue) await LoadBeatsAsync(); }
    private async void GenerateVideoPromptButton_Click(object sender, RoutedEventArgs e) { if (!RequireEpisode(out var p, out var ep) || !int.TryParse(BeatNumberTextBox.Text, out var beat)) return; var d = await RequestAsync("正在生成视频提示词…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/beats/{beat}/video-prompt/generate", new { language = "zh" }), "视频提示词生成完成"); if (d.HasValue) { BeatVisualTextBox.Text = Text(d.Value, "video_prompt", "prompt") ?? BeatVisualTextBox.Text; await LoadBeatsAsync(); } }
    private async void GenerateSketchesButton_Click(object sender, RoutedEventArgs e) { if (!RequireEpisode(out var p, out var ep)) return; var d = await RequestAsync("正在提交整集分镜生成…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/sketches/generate"), "分镜生成任务已提交"); if (d.HasValue) await LoadProductionTasksAsync(); }
    private async void RegenerateSketchButton_Click(object sender, RoutedEventArgs e) { if (!RequireEpisode(out var p, out var ep) || !int.TryParse(BeatNumberTextBox.Text, out var beat)) return; var d = await RequestAsync("正在提交分镜重绘…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/sketches/regenerate", new { beat_numbers = new[] { beat } }), "分镜重绘任务已提交"); if (d.HasValue) await LoadProductionTasksAsync(); }
    private async void UploadSketchButton_Click(object sender, RoutedEventArgs e) { if (!RequireEpisode(out var p, out var ep) || !int.TryParse(BeatNumberTextBox.Text, out var beat)) return; var file = PickFile("上传镜头分镜", "图片|*.png;*.jpg;*.jpeg;*.webp"); if (file is null) return; var d = await RequestAsync("正在上传分镜…", () => _api.UploadFileAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/beats/{beat}/sketch/upload", file), "分镜已更新"); if (d.HasValue) await LoadBeatsAsync(); }

    private async Task LoadVoicesAsync()
    {
        if (!RequireProject(out var p)) return; var data = await RequestAsync("正在读取音色…", () => _api.GetAsync($"/api/v1/projects/{E(p)}/tts/voices"), "音色已刷新", false); if (!data.HasValue) return;
        _voices.Clear(); foreach (var item in ArrayOf(data.Value, "voices", "items", "options")) _voices.Add(new VoiceRow(Text(item, "id", "voice_id", "value") ?? string.Empty, Text(item, "name", "label") ?? Text(item, "id") ?? "音色", Text(item, "language", "locale") ?? string.Empty, Text(item, "description", "detail") ?? string.Empty));
    }
    private async void RefreshVoicesButton_Click(object sender, RoutedEventArgs e) => await LoadVoicesAsync();
    private async void GenerateEpisodeAudioButton_Click(object sender, RoutedEventArgs e) { if (!RequireEpisode(out var p, out var ep)) return; var beatNumbers = int.TryParse(AudioBeatNumberTextBox.Text, out var beat) ? new[] { beat } : null; var d = await RequestAsync("正在提交音频生成…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/audio/generate", beatNumbers is null ? new { mode = "sync_changed" } : new { beat_numbers = beatNumbers, mode = "redo_selected" }), "音频生成任务已提交"); if (d.HasValue) await LoadProductionTasksAsync(); }
    private async void UploadBeatAudioButton_Click(object sender, RoutedEventArgs e) { if (!RequireEpisode(out var p, out var ep) || !int.TryParse(AudioBeatNumberTextBox.Text, out var beat)) { MessageBox.Show("请填写镜头号"); return; } var file = PickFile("上传镜头音频", "音频|*.wav;*.mp3;*.m4a;*.flac"); if (file is null) return; var d = await RequestAsync("正在上传镜头音频…", () => _api.UploadFileAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/beats/{beat}/audio", file), "镜头音频已更新"); if (d.HasValue) await LoadBeatsAsync(); }
    private async void PreviewVoiceButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p) || VoicesGrid.SelectedItem is not VoiceRow voice) { MessageBox.Show("请先选择一个音色"); return; } var d = await RequestAsync("正在生成音色试听…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/tts/preview", new { voice_id = voice.Id, text = VoicePreviewTextBox.Text.Trim() }), "试听音频已生成"); var url = d.HasValue ? Text(d.Value, "audio_url", "url") : null; if (!string.IsNullOrWhiteSpace(url)) OpenUrl(url); }

    private async Task LoadVideoBackendsAsync()
    {
        if (!RequireProject(out var p)) return; var data = await RequestAsync("正在读取视频模型…", () => _api.GetAsync($"/api/v1/projects/{E(p)}/video-backends"), "视频模型已刷新", false); if (!data.HasValue) return;
        var values = ArrayOf(data.Value, "backends", "items", "options").Select(x => new ComboBoxItem { Content = Text(x, "label", "name", "value") ?? "视频模型", Tag = Text(x, "value", "id") ?? string.Empty }).ToList();
        VideoBackendComboBox.ItemsSource = values; VideoBackendComboBox.SelectedItem = values.FirstOrDefault(x => Boolean(ArrayOf(data.Value, "backends", "items", "options").ElementAtOrDefault(values.IndexOf(x)), "is_default")) ?? values.FirstOrDefault();
    }
    private async Task LoadVideoPoolAsync()
    {
        if (!RequireEpisode(out var p, out var ep)) return; var data = await RequestAsync("正在读取视频池…", () => _api.GetAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/video-pool"), "视频池已刷新", false); if (!data.HasValue) return;
        _videoPool.Clear(); foreach (var item in ArrayOf(data.Value, "entries", "videos", "items", "pool")) _videoPool.Add(new VideoCandidateRow(Number(item, "beat_num", "beat", "beat_number"), Text(item, "id", "pool_id") ?? string.Empty, Text(item, "status") ?? string.Empty, Text(item, "video_url", "url", "video_path") ?? string.Empty));
    }
    private async void LoadVideoPoolButton_Click(object sender, RoutedEventArgs e) => await LoadVideoPoolAsync();
    private void VideoPoolGrid_SelectionChanged(object sender, SelectionChangedEventArgs e) { if (VideoPoolGrid.SelectedItem is VideoCandidateRow row) VideoBeatNumberTextBox.Text = row.Beat.ToString(); }
    private async void GenerateBeatVideoButton_Click(object sender, RoutedEventArgs e) { if (!RequireEpisode(out var p, out var ep) || !int.TryParse(VideoBeatNumberTextBox.Text, out var beat)) { MessageBox.Show("请填写镜头号"); return; } var backend = (VideoBackendComboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString(); var d = await RequestAsync("正在提交镜头视频生成…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/beats/{beat}/video", new { video_backend = backend, prompt = VideoPromptTextBox.Text.Trim(), use_director_render = false }), "视频生成任务已提交"); if (d.HasValue) await LoadProductionTasksAsync(); }
    private async void SelectVideoCandidateButton_Click(object sender, RoutedEventArgs e) { if (!RequireEpisode(out var p, out var ep) || VideoPoolGrid.SelectedItem is not VideoCandidateRow row) return; var d = await RequestAsync("正在切换采用版本…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/beats/{row.Beat}/video-pool-select", new { pool_id = row.Id }), "采用版本已更新"); if (d.HasValue) await LoadVideoPoolAsync(); }
    private async void UploadBeatVideoButton_Click(object sender, RoutedEventArgs e) { if (!RequireEpisode(out var p, out var ep) || !int.TryParse(VideoBeatNumberTextBox.Text, out var beat)) return; var file = PickFile("上传镜头视频", "视频|*.mp4;*.mov;*.webm;*.mkv"); if (file is null) return; var d = await RequestAsync("正在上传镜头视频…", () => _api.UploadFileAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/beats/{beat}/video", file), "镜头视频已更新"); if (d.HasValue) await LoadVideoPoolAsync(); }
    private void OpenVideoButton_Click(object sender, RoutedEventArgs e) { if (VideoPoolGrid.SelectedItem is VideoCandidateRow row && !string.IsNullOrWhiteSpace(row.Url)) OpenUrl(row.Url); }

    private async void PlanRenderButton_Click(object sender, RoutedEventArgs e) { if (!RequireEpisode(out var p, out var ep)) return; var indices = _beats.Select(b => b.Number).ToArray(); var d = await RequestAsync("正在生成渲染计划…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/render/plan", new { beat_indices = indices, strategy = "location", force_one_by_one = false, aspect_mode = "9:16", sketch_aspect_padding = true }), "渲染计划已生成"); if (d.HasValue) { _lastRenderPlan = d.Value.Clone(); FinalResultTextBox.Text = Format(d.Value); FinalStatusText.Text = "计划已就绪"; } }
    private async void ExecuteRenderButton_Click(object sender, RoutedEventArgs e) { if (!RequireEpisode(out var p, out var ep)) return; if (!_lastRenderPlan.HasValue) { MessageBox.Show("请先生成渲染计划"); return; } var plan = _lastRenderPlan.Value; var body = new { plan = Property(plan, "plan") ?? plan, plan_hash = Text(plan, "plan_hash") ?? string.Empty, input_fingerprint = Text(plan, "input_fingerprint") ?? string.Empty, strategy = "location", aspect_mode = "9:16", beat_indices = _beats.Select(b => b.Number).ToArray(), custom_plan = false }; var d = await RequestAsync("正在执行渲染…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/render/execute", body), "渲染任务已提交"); if (d.HasValue) { FinalResultTextBox.Text = Format(d.Value); await LoadProductionTasksAsync(); } }
    private async void ComposeVideoButton_Click(object sender, RoutedEventArgs e) { if (!RequireEpisode(out var p, out var ep)) return; var d = await RequestAsync("正在提交成片合成…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/videos/compose", new { add_subtitles = true, add_bgm = true, resolution = "1080p" }), "成片合成任务已提交"); if (d.HasValue) { FinalStatusText.Text = "合成中"; await LoadProductionTasksAsync(); } }
    private async Task LoadFinalAsync() { if (!RequireEpisode(out var p, out var ep)) return; var d = await RequestAsync("正在读取成片结果…", () => _api.GetAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/final"), "成片结果已刷新", false); if (d.HasValue) { FinalResultTextBox.Text = Format(d.Value); FinalStatusText.Text = Boolean(d.Value, "exists") ? "成片已就绪" : "尚未合成"; } }
    private async void LoadFinalButton_Click(object sender, RoutedEventArgs e) => await LoadFinalAsync();
    private async void DownloadVideoButton_Click(object sender, RoutedEventArgs e) => await DownloadExportAsync("video", "MP4 视频|*.mp4", ".mp4");
    private async void DownloadSrtButton_Click(object sender, RoutedEventArgs e) => await DownloadExportAsync("srt", "SRT 字幕|*.srt", ".srt");
    private async void DownloadZipButton_Click(object sender, RoutedEventArgs e) => await DownloadExportAsync("zip", "ZIP 工程包|*.zip", ".zip", true);
    private async Task DownloadExportAsync(string kind, string filter, string extension, bool post = false)
    {
        if (!RequireEpisode(out var p, out var ep)) return; var dialog = new SaveFileDialog { Filter = filter, FileName = $"{p}-EP{ep:000}-{kind}{extension}" }; if (dialog.ShowDialog(Window.GetWindow(this)) != true) return;
        SetBusy(true, "正在下载导出文件…"); try { var result = post ? await _api.DownloadPostAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/export/{kind}", dialog.FileName) : await _api.DownloadAsync($"/api/v1/projects/{E(p)}/episodes/{ep}/export/{kind}", dialog.FileName); if (!result.IsSuccess) MessageBox.Show(result.Message); else { ProductionStatusText.Text = $"已保存：{dialog.FileName}"; Process.Start(new ProcessStartInfo("explorer.exe", $"/select,\"{dialog.FileName}\"") { UseShellExecute = true }); } } finally { SetBusy(false); }
    }

    private async Task LoadAssetsAsync()
    {
        if (!RequireProject(out var p)) return; var d = await RequestAsync("正在读取素材资产…", () => _api.GetAsync($"/api/v1/projects/{E(p)}/freezone/assets"), "素材资产已刷新", false); if (!d.HasValue) return;
        _assets.Clear(); foreach (var item in ArrayOf(d.Value, "assets", "items")) _assets.Add(new AssetRow(Text(item, "id") ?? Guid.NewGuid().ToString("N"), Text(item, "tab", "category") ?? string.Empty, Text(item, "kind", "role") ?? string.Empty, Text(item, "label", "name") ?? "素材", Text(item, "media_type") ?? string.Empty, !item.TryGetProperty("exists", out _) || Boolean(item, "exists"), Text(item, "url", "rel_path") ?? string.Empty)); ApplyAssetFilter();
    }
    private async void RefreshAssetsButton_Click(object sender, RoutedEventArgs e) => await LoadAssetsAsync();
    private void AssetFilterTextBox_TextChanged(object sender, TextChangedEventArgs e) => ApplyAssetFilter();
    private void ApplyAssetFilter() { var q = AssetFilterTextBox?.Text.Trim() ?? string.Empty; _filteredAssets.Clear(); foreach (var asset in _assets.Where(a => q.Length == 0 || a.Label.Contains(q, StringComparison.OrdinalIgnoreCase) || a.Kind.Contains(q, StringComparison.OrdinalIgnoreCase) || a.Category.Contains(q, StringComparison.OrdinalIgnoreCase))) _filteredAssets.Add(asset); }
    private void OpenAssetButton_Click(object sender, RoutedEventArgs e) { if (AssetsGrid.SelectedItem is AssetRow row && !string.IsNullOrWhiteSpace(row.Url)) OpenUrl(row.Url); }

    private async Task LoadCanvasesAsync()
    {
        if (!RequireProject(out var p)) return; var d = await RequestAsync("正在读取自由画布…", () => _api.GetAsync($"/api/v1/projects/{E(p)}/freezone/canvases"), "画布已刷新", false); if (!d.HasValue) return;
        _canvases.Clear(); foreach (var item in ArrayOf(d.Value, "canvases", "items")) _canvases.Add(new CanvasRow(Text(item, "canvas_id", "id") ?? string.Empty, Text(item, "display_name", "name") ?? Text(item, "canvas_id") ?? "画布", Date(item, "updated_at", "modified_at")));
    }
    private async void RefreshCanvasesButton_Click(object sender, RoutedEventArgs e) => await LoadCanvasesAsync();
    private void NewCanvasButton_Click(object sender, RoutedEventArgs e) { var id = $"canvas-{DateTime.Now:yyyyMMdd-HHmmss}"; CanvasIdTextBox.Text = id; CanvasNameTextBox.Text = "新画布"; CanvasJsonTextBox.Text = "{\n  \"viewport\": { \"x\": 0, \"y\": 0, \"zoom\": 1 },\n  \"nodes\": [],\n  \"edges\": []\n}"; }
    private async void CanvasesGrid_SelectionChanged(object sender, SelectionChangedEventArgs e) { if (CanvasesGrid.SelectedItem is CanvasRow row) { CanvasIdTextBox.Text = row.Id; CanvasNameTextBox.Text = row.Name; await LoadCanvasAsync(); } }
    private async Task LoadCanvasAsync() { if (!RequireProject(out var p) || CanvasIdTextBox.Text.Trim().Length == 0) return; var d = await RequestAsync("正在读取画布内容…", () => _api.GetAsync($"/api/v1/projects/{E(p)}/freezone/canvases/{E(CanvasIdTextBox.Text.Trim())}"), "画布已读取", false); if (d.HasValue) CanvasJsonTextBox.Text = Format(d.Value); }
    private async void LoadCanvasButton_Click(object sender, RoutedEventArgs e) => await LoadCanvasAsync();
    private async void SaveCanvasButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p)) return; var id = CanvasIdTextBox.Text.Trim(); if (id.Length == 0) { MessageBox.Show("请填写画布 ID"); return; } var raw = ParseDictionary(CanvasJsonTextBox.Text); if (raw is null) { MessageBox.Show("请修正画布 JSON 格式"); return; } raw["schema_version"] = 2; raw["canvas_id"] = id; raw["project_id"] = p; raw["client_save_id"] = $"native-{Guid.NewGuid():N}"; raw["save_source"] = "manual_save"; raw["metadata"] = new { canvas_origin = "user_created", display_name = CanvasNameTextBox.Text.Trim() }; var d = await RequestAsync("正在保存画布…", () => _api.PutAsync($"/api/v1/projects/{E(p)}/freezone/canvases/{E(id)}", raw), "画布已保存"); if (d.HasValue) await LoadCanvasesAsync(); }
    private async void DeleteCanvasButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p) || CanvasIdTextBox.Text.Trim().Length == 0) return; var d = await RequestAsync("正在删除画布…", () => _api.DeleteAsync($"/api/v1/projects/{E(p)}/freezone/canvases/{E(CanvasIdTextBox.Text.Trim())}"), "画布已删除"); if (d.HasValue) await LoadCanvasesAsync(); }
    private async void CanvasHistoryButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p) || CanvasIdTextBox.Text.Trim().Length == 0) return; var d = await RequestAsync("正在读取画布历史…", () => _api.GetAsync($"/api/v1/projects/{E(p)}/freezone/canvases/{E(CanvasIdTextBox.Text.Trim())}/history"), "画布历史已读取"); if (d.HasValue) MessageBox.Show(Format(d.Value), "画布历史"); }

    private async Task LoadSkillsAsync()
    {
        var d = await RequestAsync("正在读取 AI 技能…", () => _api.GetAsync("/api/v1/freezone/skills"), "AI 技能已刷新", false); if (!d.HasValue) return;
        _skills.Clear(); foreach (var item in ArrayOf(d.Value, "skills", "items")) { var inputs = ArrayOf(item, "inputs"); var role = inputs.FirstOrDefault().ValueKind == JsonValueKind.Object ? Text(inputs.First(), "role") ?? "prompt" : "prompt"; _skills.Add(new SkillRow(Text(item, "id", "skill_id") ?? string.Empty, Text(item, "name", "label", "title") ?? Text(item, "id") ?? "AI 技能", Text(item, "description") ?? string.Empty, role)); } SkillComboBox.SelectedIndex = _skills.Count > 0 ? 0 : -1;
    }
    private async void RunSkillButton_Click(object sender, RoutedEventArgs e)
    {
        if (!RequireProject(out var p) || SkillComboBox.SelectedItem is not SkillRow skill) { MessageBox.Show("请选择 AI 技能"); return; }
        var parameters = ParseDictionary(SkillParametersTextBox.Text) ?? new Dictionary<string, object?>(); var nodeId = $"native-input-{Guid.NewGuid():N}"; var body = new { schema_version = "skill_run.v1", skill_node_id = $"native-skill-{Guid.NewGuid():N}", canvas_id = "native-tools", idempotency_key = $"native-{Guid.NewGuid():N}", resolved_inputs = new[] { new { role = skill.InputRole, node_id = nodeId, node_type = "text", text = SkillPromptTextBox.Text.Trim(), media_kind = "text" } }, parameters };
        var d = await RequestAsync("正在执行 AI 技能…", () => _api.PostAsync($"/api/v1/projects/{E(p)}/freezone/skills/{E(skill.Id)}/run", body), "AI 技能已提交"); if (d.HasValue) { SkillResultTextBox.Text = Format(d.Value); await LoadProductionTasksAsync(); }
    }

    private async Task LoadProductionTasksAsync()
    {
        if (!RequireProject(out var p)) return; var d = await RequestAsync("正在读取生产任务…", () => _api.GetAsync($"/api/v1/projects/{E(p)}/tasks"), "生产任务已刷新", false); if (!d.HasValue) return;
        _productionTasks.Clear(); foreach (var item in ArrayOf(d.Value, "tasks", "items")) _productionTasks.Add(new ProductionTaskRow(Text(item, "task_type", "type") ?? "任务", Text(item, "status") ?? "unknown", Number(item, "episode"), NullableNumber(item, "beat_num", "beat"), Text(item, "scope") ?? string.Empty, Decimal(item, "progress"), Text(item, "current_task", "message") ?? string.Empty, Text(item, "error") ?? string.Empty, Date(item, "updated_at", "created_at")));
    }
    private async void RefreshProductionTasksButton_Click(object sender, RoutedEventArgs e) => await LoadProductionTasksAsync();
    private async void ClearProductionTasksButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p)) return; var d = await RequestAsync("正在清理已完成任务…", () => _api.DeleteAsync($"/api/v1/projects/{E(p)}/tasks/completed"), "已完成任务已清理"); if (d.HasValue) await LoadProductionTasksAsync(); }
    private async void CancelProductionTaskButton_Click(object sender, RoutedEventArgs e) { if (!RequireProject(out var p) || ProductionTasksGrid.SelectedItem is not ProductionTaskRow row) return; var query = row.Beat.HasValue ? $"?beat_num={row.Beat}" : string.Empty; if (!string.IsNullOrWhiteSpace(row.Scope)) query += (query.Length == 0 ? "?" : "&") + $"scope={E(row.Scope)}"; var d = await RequestAsync("正在取消或删除任务…", () => _api.DeleteAsync($"/api/v1/projects/{E(p)}/tasks/{E(row.Type)}/{row.Episode}{query}"), "任务已取消或删除"); if (d.HasValue) await LoadProductionTasksAsync(); }

    private string? PickFile(string title, string filter) { var dialog = new OpenFileDialog { Title = title, Filter = filter + "|所有文件|*.*" }; return dialog.ShowDialog(Window.GetWindow(this)) == true ? dialog.FileName : null; }
    private void OpenUrl(string url) { try { Process.Start(new ProcessStartInfo(_api.ResolveUri(url).ToString()) { UseShellExecute = true }); } catch (Exception error) { MessageBox.Show(error.Message); } }
    private static object JsonOrPrompt(string text) => ParseJson(text) ?? new { prompt = text.Trim(), description = text.Trim() };
    private static object? ParseJson(string text) { try { using var doc = JsonDocument.Parse(text); return doc.RootElement.Clone(); } catch (JsonException) { return null; } }
    private static Dictionary<string, object?>? ParseDictionary(string text) { try { return JsonSerializer.Deserialize<Dictionary<string, object?>>(text); } catch (JsonException) { return null; } }
    private static string Format(JsonElement element) => JsonSerializer.Serialize(element, PrettyJson);
    private static JsonElement? Property(JsonElement element, string name) => element.ValueKind == JsonValueKind.Object && element.TryGetProperty(name, out var value) ? value.Clone() : null;
    private static IReadOnlyList<JsonElement> ArrayOf(JsonElement element, params string[] names)
    {
        if (element.ValueKind == JsonValueKind.Array) return element.EnumerateArray().Select(x => x.Clone()).ToArray();
        if (element.ValueKind == JsonValueKind.Object)
        {
            foreach (var name in names) if (element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Array) return value.EnumerateArray().Select(x => x.Clone()).ToArray();
        }
        return [];
    }
    private static string? Text(JsonElement element, params string[] names) { if (element.ValueKind != JsonValueKind.Object) return null; foreach (var name in names) { if (!element.TryGetProperty(name, out var value)) continue; if (value.ValueKind == JsonValueKind.String) return value.GetString(); if (value.ValueKind is JsonValueKind.Number or JsonValueKind.True or JsonValueKind.False) return value.ToString(); } return null; }
    private static int Number(JsonElement element, params string[] names) => NullableNumber(element, names) ?? 0;
    private static int? NullableNumber(JsonElement element, params string[] names) { if (element.ValueKind != JsonValueKind.Object) return null; foreach (var name in names) { if (!element.TryGetProperty(name, out var value)) continue; if (value.ValueKind == JsonValueKind.Number && value.TryGetInt32(out var number)) return number; if (value.ValueKind == JsonValueKind.String && int.TryParse(value.GetString(), out number)) return number; } return null; }
    private static double Decimal(JsonElement element, params string[] names) { if (element.ValueKind != JsonValueKind.Object) return 0; foreach (var name in names) { if (!element.TryGetProperty(name, out var value)) continue; if (value.ValueKind == JsonValueKind.Number && value.TryGetDouble(out var number)) return number; if (value.ValueKind == JsonValueKind.String && double.TryParse(value.GetString(), out number)) return number; } return 0; }
    private static bool Boolean(JsonElement element, string name) { if (element.ValueKind != JsonValueKind.Object || !element.TryGetProperty(name, out var value)) return false; return value.ValueKind == JsonValueKind.True || value.ValueKind == JsonValueKind.String && bool.TryParse(value.GetString(), out var parsed) && parsed; }
    private static DateTimeOffset? Date(JsonElement element, params string[] names) { var text = Text(element, names); return DateTimeOffset.TryParse(text, out var value) ? value : null; }
}
