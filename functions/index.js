const { onDocumentWritten } = require("firebase-functions/v2/firestore");
const { initializeApp } = require("firebase-admin/app");
const nodemailer = require("nodemailer");
require("dotenv").config();

initializeApp();

// 🔐 Gmail credentials
const gmailUser = process.env.USER_EMAIL;
const gmailPass = process.env.USER_PASS;

// Safety check
if (!gmailUser || !gmailPass) {
  console.warn("⚠️ Gmail credentials not found! Emails will not be sent.");
}

const transporter = nodemailer.createTransport({
  service: "gmail",
  auth: {
    user: gmailUser,
    pass: gmailPass,
  },
});

// 📨 Firestore trigger: when a user's KYC status changes
exports.sendKycStatusEmail = onDocumentWritten("users/{userId}", async (event) => {
  const before = event.data.before?.data();
  const after = event.data.after?.data();

  // Only trigger if KYC status actually changed
  if (!before || !after || before.kycStatus === after.kycStatus) return;

  const userEmail = after.email;
  const userName = after.fullName || "User";
  const status = after.kycStatus;

  let subject = "";
  let message = "";

  if (status === "approved") {
    subject = "✅ Your BahAI KYC Has Been Approved!";
    message = `
      Hi ${userName},<br><br>
      Great news! Your KYC verification has been <b>approved</b>.<br>
      You can now log in to your BahAI account and access all features.<br><br>
      <a href="http://127.0.0.1:5500/public/login.html">Login Here</a><br><br>
      Regards,<br>
      The BahAI Team
    `;
  } else if (status === "rejected") {
    subject = "❌ Your BahAI KYC Has Been Rejected";
    message = `
      Hi ${userName},<br><br>
      Unfortunately, your KYC verification was <b>rejected</b>.<br>
      Please review your ID or selfie and try again.<br><br>
      Regards,<br>
      The BahAI Team
    `;
  } else {
    return;
  }

  try {
    await transporter.sendMail({
      from: `"BahAI Verification" <${gmailUser}>`,
      to: userEmail,
      subject,
      html: message,
    });
    console.log(`✅ Email sent to ${userEmail} (${status})`);
  } catch (error) {
    console.error("❌ Failed to send email:", error);
  }
});
