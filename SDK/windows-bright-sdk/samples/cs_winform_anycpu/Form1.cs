using System;
using System.Windows.Forms;

namespace cs_winform_anycpu {
    public partial class Form1 : Form {
        BrightData.Api sdk = new BrightData.Api();
        public Form1() {
            InitializeComponent();
            sdk.ConsentChoiceChanged += sdk_ConsentChoiceChanged;            
            sdk.ConsentDialogShown += OnShown;
            sdk.ConsentDialogClosed += OnClosed;
            sdk.Init(new BrightData.Api.Settings {
                AppId ="win_myapp.example.com",
            });
        }
        private void OnClosed(object sender, object args) {
            Invoke((Action)(() => {
                MessageBox.Show(this, "Consent dialog closed", "Info");
            }));
        }
        private void OnShown(object sender, object args) {
            Invoke((Action)(() => {
                MessageBox.Show(this, "Consent dialog shown", "Info");
            }));
        }
        private void btnShowConsent_Click(object sender, EventArgs e) {
            sdk.ShowConsent();
        }
        private void btnOptOut_Click(object sender, EventArgs e) {
            sdk.OptOut();
        }
        private void btnStatus_Click(object sender, EventArgs e) {
            UpdateChoice(sdk.ConsentChoice);
        }
        private void sdk_ConsentChoiceChanged(object sender, BrightData.Api.ConsentChoiceChangedEventArgs e){
            UpdateChoice(e.Choice);
        }
        private void UpdateChoice(bool? choice) {
            var s =
                choice == true ? "Peer" :
                choice == false ? "Not Peer" :
                "No Selection";
            lblChoice.Text = "Consent choice: "+s;
        }
        private void Form1_FormClosed(object sender, FormClosedEventArgs e) {
            sdk.Close();
        }
    }
}
