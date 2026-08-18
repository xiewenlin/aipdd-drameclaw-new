using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;

namespace Gulong.ShortDrama;

public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        RenderOptions.ProcessRenderMode = RenderMode.SoftwareOnly;
        base.OnStartup(e);
        DispatcherUnhandledException += (_, args) =>
        {
            MessageBox.Show(args.Exception.Message, "古龙短剧", MessageBoxButton.OK, MessageBoxImage.Error);
            args.Handled = true;
        };
    }
}
