package com.example.pick_dream.ui.mypage.inquiry

import android.os.Bundle
import android.widget.ImageButton
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import com.example.pick_dream.R
import com.example.pick_dream.ui.login.AuthenticatedEntryGuard

class InquiryActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (AuthenticatedEntryGuard.redirectToLoginIfRequired(this)) return
        enableEdgeToEdge()
        setContentView(R.layout.activity_inquiry)

        val backButton = findViewById<ImageButton>(R.id.backButton)
        backButton.setOnClickListener {
            finish()
        }

    }
}
