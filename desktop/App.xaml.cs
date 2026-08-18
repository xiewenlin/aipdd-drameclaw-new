using System.Windows;

namespace Gulong.ShortDrama;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        DispatcherUnhandledException += (_, args) =>
        {
            MessageBox.Show(args.Exception.Message, "古龙短剧", MessageBoxButton.OK, MessageBoxImage.Error);
            args.Handled = true;
        };
    }
}
