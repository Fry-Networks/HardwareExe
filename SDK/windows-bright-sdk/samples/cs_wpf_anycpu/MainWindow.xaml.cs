using System.ComponentModel;
using System.Windows;
using lum_sdk;
using System.Collections.ObjectModel;
using System.Windows.Controls;
using System;
using System.Linq;

namespace cs_wpf_anycpu {
    partial class MainWindow : Window, INotifyPropertyChanged {
        private BrightData.Api sdk = new BrightData.Api();
        public ObservableCollection<ComboBoxItem> cmb_appid { get; set; }
        public ComboBoxItem cmb_appid_sel { get; set; }
        public ObservableCollection<ComboBoxItem> cmb_txt_culture { get; set; }
        public ComboBoxItem cmb_txt_culture_sel { get; set; }
        public ObservableCollection<ComboBoxItem> cmb_not_peer_txt { get; set; }
        public ComboBoxItem cmb_not_peer_txt_sel { get; set; }
        public MainWindow() {
            InitializeComponent();
            DataContext = this;
            _choice = "Make your choice";
            cmb_appid = new ObservableCollection<ComboBoxItem> {
                new ComboBoxItem { Content = "win_myapp.example.com" },
                new ComboBoxItem { Content = "win_av.example.org" },
                new ComboBoxItem { Content = "win_beta.example.com" }
            };
            cmb_appid_sel = cmb_appid.First();
            cmb_txt_culture = new ObservableCollection<ComboBoxItem> {
                new ComboBoxItem { Content = "Default" },
                new ComboBoxItem { Content = "en-US" },
                new ComboBoxItem { Content = "de-DE" },
                new ComboBoxItem { Content = "es-ES" },
                new ComboBoxItem { Content = "fr-FR" },
                new ComboBoxItem { Content = "it-IT" },
                new ComboBoxItem { Content = "pt-PT" },
                new ComboBoxItem { Content = "ru-RU" },
                new ComboBoxItem { Content = "zh-CH" }
            };
            cmb_txt_culture_sel = cmb_txt_culture.First();
            cmb_not_peer_txt = new ObservableCollection<ComboBoxItem>(
                Enum.GetValues(typeof(BrightData.Api.DisagreeButtonText))
                    .Cast<object>()
                    .Select(t => new ComboBoxItem { Content = t }));

            sdk.ConsentChoiceChanged += sdk_ConsentChoiceChanged;
            sdk.ConsentDialogShown += OnShown;
            sdk.ConsentDialogClosed += OnClosed;
            sdk.Init(new BrightData.Api.Settings {
                AppId = cmb_appid_sel.Content as string,
                DisagreeButtonText = (BrightData.Api.DisagreeButtonText?)cmb_not_peer_txt_sel?.Content,
                SkipConsent = true,
            });
        }
        private void OnClosed(object sender, object args) {
            Debug.WriteLine("Consent dialog closed");
        }
        private void OnShown(object sender, object args) {
            Debug.WriteLine("Consent dialog shown");
        }
        private string _choice;
        public event PropertyChangedEventHandler PropertyChanged;
        public string choice {
            get { return _choice; }
            set {
                _choice = value;
                if (PropertyChanged!=null)
                    PropertyChanged(this, new PropertyChangedEventArgs("choice"));
            }
        }
        public relay_cmd show_consent {
            get {
                return new relay_cmd(o => {
                    api.set_dlg_pos(this.Top+20, this.Left+20);
                    string s = cmb_txt_culture_sel.Content as string;
                    api.set_txt_culture(s=="Default" ? null : s);
                    sdk.ShowConsent();
                });
            }
        }
        public relay_cmd opt_out {
            get { return new relay_cmd(o => sdk.OptOut()); }
        }
        public relay_cmd close {
            get { return new relay_cmd(o => sdk.Close()); }
        }
        private void sdk_ConsentChoiceChanged(object sender, BrightData.Api.ConsentChoiceChangedEventArgs e){
            update_choice(e.Choice);
        }
        private void update_choice(bool? api_choice) {
            var s =
                api_choice == true ? "Peer" :
                api_choice == false ? "Not Peer" :
                "No Selection";
            choice = "Status: "+s;
        }
        private void Window_Closed(object sender, System.EventArgs e) {
            sdk.Close();
        }
        private void Window_LocationChanged(object sender, System.EventArgs e) {
            api.set_dlg_pos(this.Top+20, this.Left+20);
        }
    }
}
