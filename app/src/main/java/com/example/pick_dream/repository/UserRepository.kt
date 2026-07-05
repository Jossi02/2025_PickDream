package com.example.pick_dream.repository

import com.example.pick_dream.model.User
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import kotlinx.coroutines.tasks.await

object UserRepository {
    private val auth: FirebaseAuth = FirebaseAuth.getInstance()
    private val db: FirebaseFirestore = FirebaseFirestore.getInstance()

    fun getCurrentUid(): String? = auth.currentUser?.uid

    suspend fun getCurrentUser(): User? {
        val uid = getCurrentUid() ?: return null
        return db.collection("User")
            .document(uid)
            .get()
            .await()
            .toObject(User::class.java)
    }

    fun getCurrentUser(onResult: (User?) -> Unit) {
        val uid = getCurrentUid() ?: run {
            onResult(null)
            return
        }

        db.collection("User")
            .document(uid)
            .get()
            .addOnSuccessListener { document ->
                onResult(document.toObject(User::class.java))
            }
            .addOnFailureListener {
                onResult(null)
            }
    }

    suspend fun getCurrentStudentId(): String? {
        val uid = getCurrentUid() ?: return null
        val document = db.collection("User")
            .document(uid)
            .get()
            .await()

        return document.getString("studentId")
            ?: document.getString("userID")
    }

    fun getCurrentStudentId(onResult: (String?) -> Unit) {
        val uid = getCurrentUid() ?: run {
            onResult(null)
            return
        }

        db.collection("User")
            .document(uid)
            .get()
            .addOnSuccessListener { document ->
                onResult(document.getString("studentId") ?: document.getString("userID"))
            }
            .addOnFailureListener {
                onResult(null)
            }
    }
}
