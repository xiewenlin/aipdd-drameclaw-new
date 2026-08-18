using System.Collections.ObjectModel;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using Gulong.ShortDrama.Core;
using Gulong.ShortDrama.Models;
using Gulong.ShortDrama.Services;

namespace Gulong.ShortDrama;

public partial class MainWindow : Window
{
    private static readonly Regex DigitsOnly = new("^[0-9]+$");
    private readonly OfficialApiClient _api = new();
    private readonly ObservableCollection<VideoTask> _tasks = [];
    private AccountSessionService? _accountSession;
    private UserAccount? _account;

    public MainWindow()
    {
        InitializeComponent();
        TasksDataGrid.ItemsSource = _tasks;
        Loaded += MainWindow_Loaded;
        Closed += MainWindow_Closed;
        ShowView(DashboardView, DashboardNavButton);
    }

    private async void MainWindow_Loaded(object sender, RoutedEventArgs e)
    {
        _accountSession = new AccountSessionService(_api, this);
        _accountSession.ReturnedToWorkbench += async (_, _) => await RefreshAccountAsync();
        SetConnectionState("正在恢复古龙账号会话…", null);
        var result = await _accountSession.TryRestoreAsync();
        if (result.IsSuccess && result.Value is not null)
        {
            ApplyAccount(result.Value);
            SetConnectionState("已连接古龙账号", true);
        }
        else
        {
            ApplyAccount(null);
            SetConnectionState(result.Code == "AUTH_REQUIRED" ? "请登录古龙账号" : result.Message, result.Code == "AUTH_REQUIRED" ? false : null);
        }
    }

    private void MainWindow_Closed(object? sender, EventArgs e)
    {
        _accountSession?.Dispose();
        _api.Dispose();
    }

    private void ShowView(FrameworkElement view, Button activeButton)
    {
        DashboardView.Visibility = Visibility.Collapsed;
        CreateView.Visibility = Visibility.Collapsed;
        TasksView.Visibility = Visibility.Collapsed;
        view.Visibility = Visibility.Visible;

        foreach (var button in new[] { DashboardNavButton, CreateNavButton, TasksNavButton })
        {
            button.Background = button == activeButton ? new SolidColorBrush(Color.FromRgb(226, 240, 234)) : Brushes.Transparent;
            button.BorderBrush = button == activeButton ? new SolidColorBrush(Color.FromRgb(156, 185, 174)) : Brushes.Transparent;
            button.FontWeight = button == activeButton ? FontWeights.SemiBold : FontWeights.Normal;
        }
    }

    private void ApplyAccount(UserAccount? account)
    {
        _account = account;
        var authenticated = account is not null;
        LoggedOutActions.Visibility = authenticated ? Visibility.Collapsed : Visibility.Visible;
        AccountButton.Visibility = authenticated ? Visibility.Visible : Visibility.Collapsed;
        if (account is null)
        {
            DashboardBalance.Text = "¥0.00";
            DashboardMembership.Text = "未登录";
            return;
        }

        AccountName.Text = account.DisplayName;
        AccountInitial.Text = account.DisplayName[..1].ToUpperInvariant();
        AccountBalance.Text = FormatMoney(account.BalanceFen);
        DashboardBalance.Text = FormatMoney(account.BalanceFen);
        DashboardMembership.Text = account.IsMember ? "古龙会员" : "普通用户";
    }

    private async Task<bool> EnsureAuthenticatedAsync(AuthMode mode = AuthMode.Login)
    {
        if (_account is not null) return true;
        if (_accountSession is null) return false;
        SetConnectionState(mode == AuthMode.Register ? "正在打开古龙注册…" : "正在连接古龙登录…", null);
        var result = await _accountSession.EnsureAuthenticatedAsync(mode);
        if (!result.IsSuccess || result.Value is null)
        {
            if (result.Code != "AUTH_CANCELLED") MessageBox.Show(this, result.Message, "古龙账号", MessageBoxButton.OK, MessageBoxImage.Warning);
            SetConnectionState(result.Code == "AUTH_CANCELLED" ? "登录已取消" : result.Message, false);
            return false;
        }
        ApplyAccount(result.Value);
        SetConnectionState("已连接古龙账号", true);
        return true;
    }

    private async Task RefreshAccountAsync()
    {
        if (_accountSession is null) return;
        var result = await _accountSession.TryRestoreAsync();
        if (result.IsSuccess && result.Value is not null) ApplyAccount(result.Value);
    }

    private void SetConnectionState(string message, bool? connected)
    {
        HeaderStatusText.Text = message;
        FooterStatusText.Text = message;
        ConnectionDot.Fill = connected switch
        {
            true => new SolidColorBrush(Color.FromRgb(45, 151, 103)),
            false => new SolidColorBrush(Color.FromRgb(202, 81, 66)),
            null => new SolidColorBrush(Color.FromRgb(211, 155, 42)),
        };
    }

    private async void LoginButton_Click(object sender, RoutedEventArgs e) => await EnsureAuthenticatedAsync(AuthMode.Login);

    private async void RegisterButton_Click(object sender, RoutedEventArgs e) => await EnsureAuthenticatedAsync(AuthMode.Register);

    private async void AccountButton_Click(object sender, RoutedEventArgs e)
    {
        if (!await EnsureAuthenticatedAsync()) return;
        await _accountSession!.OpenAccountPageAsync();
    }

    private async void SubscriptionButton_Click(object sender, RoutedEventArgs e)
    {
        if (!await EnsureAuthenticatedAsync()) return;
        await _accountSession!.OpenSubscriptionPageAsync();
    }

    private async void RechargeButton_Click(object sender, RoutedEventArgs e)
    {
        if (!await EnsureAuthenticatedAsync()) return;
        await _accountSession!.OpenRechargePageAsync();
    }

    private void DashboardNavButton_Click(object sender, RoutedEventArgs e) => ShowView(DashboardView, DashboardNavButton);

    private void CreateNavButton_Click(object sender, RoutedEventArgs e)
    {
        ShowView(CreateView, CreateNavButton);
        PromptTextBox.Focus();
    }

    private async void TasksNavButton_Click(object sender, RoutedEventArgs e)
    {
        ShowView(TasksView, TasksNavButton);
        await LoadTasksAsync();
    }

    private async void RefreshTasksButton_Click(object sender, RoutedEventArgs e) => await LoadTasksAsync();

    private async Task LoadTasksAsync()
    {
        TasksLoadingPanel.Visibility = Visibility.Visible;
        try
        {
            if (!await EnsureAuthenticatedAsync()) return;
            SetConnectionState("正在读取视频任务…", null);
            var result = await _api.ListVideoTasksAsync();
            if (!result.IsSuccess && result.Code == "UNAUTHORIZED")
            {
                ApplyAccount(null);
                if (!await EnsureAuthenticatedAsync()) return;
                result = await _api.ListVideoTasksAsync();
            }
            if (!result.IsSuccess || result.Value is null)
            {
                SetConnectionState(result.Message, false);
                MessageBox.Show(this, result.Message, "我的任务", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            _tasks.Clear();
            foreach (var task in result.Value) _tasks.Add(task);
            TasksEmptyPanel.Visibility = _tasks.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
            SetConnectionState($"已读取 {_tasks.Count} 个视频任务", true);
        }
        finally
        {
            TasksLoadingPanel.Visibility = Visibility.Collapsed;
        }
    }

    private async void SubmitTaskButton_Click(object sender, RoutedEventArgs e)
    {
        CreateErrorText.Visibility = Visibility.Collapsed;
        if (!int.TryParse(DurationTextBox.Text, out var durationSeconds))
        {
            ShowCreateError("视频时长必须是 1–600 之间的整数");
            return;
        }

        var ratio = (AspectRatioComboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString();
        H3TaskRequest request;
        try
        {
            request = TaskContracts.Build(PromptTextBox.Text, durationSeconds, ratio);
        }
        catch (ContractValidationException error)
        {
            ShowCreateError(error.Message);
            return;
        }

        SubmitTaskButton.IsEnabled = false;
        SubmitTaskButton.Content = "正在提交…";
        try
        {
            if (!await EnsureAuthenticatedAsync()) return;
            SetConnectionState("正在向古龙官网提交任务…", null);
            var result = await _api.CreateVideoTaskAsync(request);
            if (!result.IsSuccess && result.Code == "UNAUTHORIZED")
            {
                ApplyAccount(null);
                if (!await EnsureAuthenticatedAsync()) return;
                result = await _api.CreateVideoTaskAsync(request);
            }
            if (!result.IsSuccess || result.Value is null)
            {
                if (result.Code == "INSUFFICIENT_BALANCE")
                {
                    var choice = MessageBox.Show(this, $"{result.Message}\n\n是否立即打开古龙充值？", "账户余额不足", MessageBoxButton.YesNo, MessageBoxImage.Information);
                    if (choice == MessageBoxResult.Yes) await _accountSession!.OpenRechargePageAsync();
                    return;
                }
                ShowCreateError(result.Message);
                SetConnectionState(result.Message, false);
                return;
            }

            var created = result.Value;
            PromptTextBox.Clear();
            DurationTextBox.Text = "5";
            await RefreshAccountAsync();
            SetConnectionState("视频任务已进入队列", true);
            MessageBox.Show(this,
                $"订单号：{created.Task.OrderNo}\n状态：{created.Task.StatusText}\n本次扣费：{FormatMoney(created.ChargedFen)}\n剩余余额：{FormatMoney(created.RemainingBalanceFen)}",
                "视频任务创建成功",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
            ShowView(TasksView, TasksNavButton);
            await LoadTasksAsync();
        }
        finally
        {
            SubmitTaskButton.IsEnabled = true;
            SubmitTaskButton.Content = "提交生成任务";
        }
    }

    private void ShowCreateError(string message)
    {
        CreateErrorText.Text = message;
        CreateErrorText.Visibility = Visibility.Visible;
    }

    private void DurationTextBox_PreviewTextInput(object sender, TextCompositionEventArgs e) => e.Handled = !DigitsOnly.IsMatch(e.Text);

    private void DurationTextBox_TextChanged(object sender, TextChangedEventArgs e)
    {
        if (EstimatedPriceText is null) return;
        var seconds = int.TryParse(DurationTextBox.Text, out var parsed) ? Math.Max(0, parsed) : 0;
        EstimatedPriceText.Text = FormatMoney(seconds * 20L);
    }

    private static string FormatMoney(long fen) => $"¥{fen / 100.0:F2}";
}
