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
import com.google.firebase.firestore.FirebaseFirestore
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

        // 테스트 데이터를 자동으로 세팅하는 함수 호출
        seedDatabaseIfNeeded()

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

    private fun seedDatabaseIfNeeded() {
        val prefs = getSharedPreferences("AppPrefs", MODE_PRIVATE)
        if (prefs.getBoolean("isSeeded", false)) return

        val db = FirebaseFirestore.getInstance()

        // 1. 강의실(rooms) 임시 데이터 삽입
        val rooms = listOf(
            hashMapOf("name" to "덕문관 101호", "buildingName" to "덕문관", "isAvailable" to true, "capacity" to 50, "equipment" to listOf("프로젝터", "에어컨")),
            hashMapOf("name" to "집현관 202호", "buildingName" to "집현관", "isAvailable" to true, "capacity" to 30, "equipment" to listOf("화이트보드", "마이크")),
            hashMapOf("name" to "예지관 303호", "buildingName" to "예지관", "isAvailable" to false, "capacity" to 40, "equipment" to listOf("프로젝터"))
        )
        rooms.forEach { db.collection("rooms").add(it) }

        // 2. 공지사항(Notices) 임시 데이터 삽입
        val notices = listOf(
            hashMapOf("title" to "시스템 점검 안내", "content" to "주말 새벽에 점검이 있습니다. 양해 부탁드립니다.", "createdAt" to com.google.firebase.Timestamp.now()),
            hashMapOf("title" to "새로운 강의실 오픈", "content" to "집현관 202호가 새롭게 오픈되었습니다! 앱에서 예약 가능합니다.", "createdAt" to com.google.firebase.Timestamp.now())
        )
        notices.forEach { db.collection("Notices").add(it) }

        // 3. 테스트용 유저 계정(Auth 및 Firestore) 생성
        val testId = "20201234"
        val testPw = "123456"
        val testEmail = "$testId$EMAIL_DOMAIN"

        auth.createUserWithEmailAndPassword(testEmail, testPw).addOnCompleteListener { task ->
            if (task.isSuccessful) {
                val uid = task.result?.user?.uid ?: return@addOnCompleteListener
                val user = hashMapOf(
                    "studentId" to testId,
                    "name" to "김테스트",
                    "email" to testEmail,
                    "major" to "컴퓨터공학부",
                    "phone" to "010-1234-5678"
                )
                db.collection("User").document(uid).set(user).addOnSuccessListener {
                    Toast.makeText(this, "테스트 데이터 세팅 완료! $testId / $testPw 로 로그인하세요.", Toast.LENGTH_LONG).show()
                    prefs.edit().putBoolean("isSeeded", true).apply()
                }
            } else {
                Log.e("LoginActivity", "Seed data failed: ", task.exception)
            }
        }
    }
}
