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
import com.google.firebase.auth.FirebaseAuth

class LoginActivity : AppCompatActivity() {

    private lateinit var auth: FirebaseAuth

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

        loginButton.setOnClickListener {
            val id = emailEditText.text.toString().trim()
            val password = passwordEditText.text.toString().trim()

            if (id.isEmpty() || password.isEmpty()) {
                Toast.makeText(this, "학번과 비밀번호를 입력해주세요.", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            // 학번을 이메일 형식으로 변환하여 로그인
            val dummyEmail = "$id$EMAIL_DOMAIN"
            auth.signInWithEmailAndPassword(dummyEmail, password)
                .addOnCompleteListener { task ->
                    if (task.isSuccessful) {
                        startActivity(Intent(this, MainActivity::class.java))
                        finish()
                    } else {
                        Log.e("LoginActivity", "Login failed", task.exception)
                        Toast.makeText(
                            this,
                            "로그인 실패: ${task.exception?.message}",
                            Toast.LENGTH_SHORT
                        ).show()
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
}
