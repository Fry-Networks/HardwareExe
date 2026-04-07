namespace cs_winform_anycpu {
    partial class Form1 {
        /// <summary>
        /// Required designer variable.
        /// </summary>
        private System.ComponentModel.IContainer components = null;

        /// <summary>
        /// Clean up any resources being used.
        /// </summary>
        /// <param name="disposing">true if managed resources should be disposed; otherwise, false.</param>
        protected override void Dispose(bool disposing) {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        #region Windows Form Designer generated code

        /// <summary>
        /// Required method for Designer support - do not modify
        /// the contents of this method with the code editor.
        /// </summary>
        private void InitializeComponent() {
            this.btnShowConsent = new System.Windows.Forms.Button();
            this.btnOptOut = new System.Windows.Forms.Button();
            this.btnStatus = new System.Windows.Forms.Button();
            this.lblChoice = new System.Windows.Forms.Label();
            this.SuspendLayout();
            // 
            // btnShowConsent
            // 
            this.btnShowConsent.Location = new System.Drawing.Point(48, 30);
            this.btnShowConsent.Name = "btnShowConsent";
            this.btnShowConsent.Size = new System.Drawing.Size(203, 47);
            this.btnShowConsent.TabIndex = 0;
            this.btnShowConsent.Text = "Show Consent";
            this.btnShowConsent.UseVisualStyleBackColor = true;
            this.btnShowConsent.Click += new System.EventHandler(this.btnShowConsent_Click);
            // 
            // btnOptOut
            // 
            this.btnOptOut.Location = new System.Drawing.Point(49, 96);
            this.btnOptOut.Name = "btnOptOut";
            this.btnOptOut.Size = new System.Drawing.Size(201, 52);
            this.btnOptOut.TabIndex = 1;
            this.btnOptOut.Text = "Disable Bright SDK";
            this.btnOptOut.UseVisualStyleBackColor = true;
            this.btnOptOut.Click += new System.EventHandler(this.btnOptOut_Click);
            // 
            // btnStatus
            // 
            this.btnStatus.Location = new System.Drawing.Point(49, 163);
            this.btnStatus.Name = "btnStatus";
            this.btnStatus.Size = new System.Drawing.Size(203, 48);
            this.btnStatus.TabIndex = 2;
            this.btnStatus.Text = "Refresh Choice";
            this.btnStatus.UseVisualStyleBackColor = true;
            this.btnStatus.Click += new System.EventHandler(this.btnStatus_Click);
            // 
            // lblChoice
            // 
            this.lblChoice.Anchor = ((System.Windows.Forms.AnchorStyles)(((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Left) 
            | System.Windows.Forms.AnchorStyles.Right)));
            this.lblChoice.AutoSize = true;
            this.lblChoice.Location = new System.Drawing.Point(46, 226);
            this.lblChoice.Name = "lblChoice";
            this.lblChoice.Size = new System.Drawing.Size(81, 13);
            this.lblChoice.TabIndex = 3;
            this.lblChoice.Text = "Consent choice";
            // 
            // Form1
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 13F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(284, 261);
            this.Controls.Add(this.lblChoice);
            this.Controls.Add(this.btnStatus);
            this.Controls.Add(this.btnOptOut);
            this.Controls.Add(this.btnShowConsent);
            this.Name = "Form1";
            this.Text = "Form1";
            this.FormClosed += new System.Windows.Forms.FormClosedEventHandler(this.Form1_FormClosed);
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion

        private System.Windows.Forms.Button btnShowConsent;
        private System.Windows.Forms.Button btnOptOut;
        private System.Windows.Forms.Button btnStatus;
        private System.Windows.Forms.Label lblChoice;
    }
}

