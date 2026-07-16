package com.example.pick_dream.repository

import com.example.pick_dream.model.User
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

object UserRepository {
    private val auth: FirebaseAuth = FirebaseAuth.getInstance()
    private val db: FirebaseFirestore = FirebaseFirestore.getInstance()
    private val callbackScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    fun getCurrentUid(): String? = auth.currentUser?.uid

    suspend fun getCurrentUser(): User? {
        val uid = getCurrentUid() ?: return null
        return db.collection("User")
            .document(uid)
            .get()
            .awaitWithTimeout()
            .toObject(User::class.java)
    }

    fun getCurrentUser(onResult: (User?) -> Unit) {
        val uid = getCurrentUid() ?: run {
            onResult(null)
            return
        }

        callbackScope.launch {
            onResult(runCatching { getCurrentUser() }.getOrNull())
        }
    }

    suspend fun getCurrentStudentId(): String? {
        val uid = getCurrentUid() ?: return null
        val document = db.collection("User")
            .document(uid)
            .get()
            .awaitWithTimeout()

        return document.getString("studentId")
            ?: document.getString("userID")
    }

    fun getCurrentStudentId(onResult: (String?) -> Unit) {
        val uid = getCurrentUid() ?: run {
            onResult(null)
            return
        }

        callbackScope.launch {
            onResult(runCatching { getCurrentStudentId() }.getOrNull())
        }
    }
}
