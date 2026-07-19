package com.example.pick_dream.ui.login

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.util.Log
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.example.pick_dream.MainActivity
import com.example.pick_dream.R
import com.example.pick_dream.repository.NetworkStatus
import com.example.pick_dream.repository.networkFailure
import com.example.pick_dream.repository.repositoryFailure
import com.google.android.material.checkbox.MaterialCheckBox
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseAuthInvalidCredentialsException
import com.google.firebase.auth.FirebaseAuthInvalidUserException

class LoginActivity : AppCompatActivity() {

    private lateinit var auth: FirebaseAuth
    private lateinit var autoLoginCheckBox: MaterialCheckBox
    private var hasNavigatedToMain = false

    // 학번을 Firebase Auth 이메일로 변환하기 위한 도메인
    private val EMAIL_DOMAIN = "@example.com"
    // 비밀번호 분실 시 열어줄 학교 포털 URL
    private val PORTAL_URL = "https://kutis.kyonggi.ac.kr/webkutis/view/indexWeb.jsp"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_login)

        auth = FirebaseAuth.getInstance()

        val emailEditText = findViewById<EditText>(R.id.editTextId)
        val passwordEditText = findViewById<EditText>(R.id.editTextPassword)
        val loginButton = findViewById<Button>(R.id.buttonLogin)
        val forgotPasswordTextView = findViewById<TextView>(R.id.tvForgotPassword)
        autoLoginCheckBox = findViewById(R.id.checkBoxAutoLogin)
        autoLoginCheckBox.isChecked = AutoLoginPreferences.isEnabled(this)

        loginButton.setOnClickListener {
            val id = emailEditText.text.toString().trim()
            val password = passwordEditText.text.toString().trim()

            if (id.isEmpty() || password.isEmpty()) {
                Toast.makeText(this, "학번과 비밀번호를 입력해주세요.", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            if (!NetworkStatus.hasValidatedInternet()) {
                Toast.makeText(
                    this,
                    networkFailure("로그인").userMessage,
                    Toast.LENGTH_SHORT
                ).show()
                return@setOnClickListener
            }

            // 학번을 이메일 형식으로 변환하여 로그인
            val dummyEmail = "$id$EMAIL_DOMAIN"
            loginButton.isEnabled = false
            auth.signInWithEmailAndPassword(dummyEmail, password)
                .addOnCompleteListener { task ->
                    loginButton.isEnabled = true
                    if (task.isSuccessful) {
                        AutoLoginPreferences.setEnabled(this, autoLoginCheckBox.isChecked)
                        navigateToMain()
                    } else {
                        Log.e("LoginActivity", "Login failed", task.exception)
                        val message = when (val error = task.exception) {
                            is FirebaseAuthInvalidCredentialsException,
                            is FirebaseAuthInvalidUserException -> "학번 또는 비밀번호를 확인해 주세요."
                            null -> "로그인에 실패했습니다. 다시 시도해 주세요."
                            else -> repositoryFailure("로그인", error).userMessage
                        }
                        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
                    }
                }
        }

        forgotPasswordTextView.setOnClickListener {
            try {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(PORTAL_URL)))
            } catch (e: Exception) {
                Log.e("LoginActivity", "Failed to open browser", e)
                Toast.makeText(this, "브라우저를 열 수 없습니다.", Toast.LENGTH_SHORT).show()
            }
        }
    }

    override fun onStart() {
        super.onStart()
        val shouldEnterApp = AutoLoginDecider.shouldEnterApp(
            isEnabled = AutoLoginPreferences.isEnabled(this),
            hasAuthenticatedUser = auth.currentUser != null,
            hasActiveSession = ActiveLoginSession.isAuthorized()
        )
        if (shouldEnterApp) {
            navigateToMain()
        }
    }

    private fun navigateToMain() {
        if (hasNavigatedToMain) return
        hasNavigatedToMain = true
        ActiveLoginSession.authorize()
        startActivity(
            Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            }
        )
        finish()
    }
}
