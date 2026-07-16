package com.example.pick_dream.ui.home.notice

import com.example.pick_dream.model.Notice
import com.example.pick_dream.repository.RepositoryResult
import com.example.pick_dream.repository.awaitWithTimeout
import com.example.pick_dream.repository.repositoryFailure
import com.google.firebase.firestore.ktx.firestore
import com.google.firebase.ktx.Firebase
import java.text.SimpleDateFormat
import java.util.Locale

object NoticeRepository {
    private val db = Firebase.firestore
    private val formatter = SimpleDateFormat("yy.MM.dd", Locale.getDefault())

    /**
     * Firestore에서 모든 공지사항을 가져옵니다.
     */
    suspend fun fetchAllNotices(): RepositoryResult<List<Notice>> {
        return try {
            val result = db.collection("Notices").get().awaitWithTimeout()
            RepositoryResult.Success(result.map { doc ->
                val timestamp = doc.getTimestamp("createdAt")
                val formattedDate = timestamp?.toDate()?.let { formatter.format(it) } ?: ""

                Notice(
                    id = doc.id,
                    iconEmoji = "📢", // 기본 이모지, 뷰모델/어댑터에서 타이틀에 따라 이벤트 아이콘으로 변경 가능
                    title = doc.getString("title") ?: "",
                    date = formattedDate,
                    content = doc.getString("content") ?: ""
                )
            }.sortedByDescending { it.date }) // 최신순 정렬 보장
        } catch (e: Exception) {
            RepositoryResult.Error(repositoryFailure("공지사항 조회", e))
        }
    }

    /**
     * Firestore에서 가장 최근 공지사항 1개를 가져옵니다.
     */
    suspend fun fetchLatestNotice(): RepositoryResult<Notice?> {
        return try {
            val result = db.collection("Notices")
                .orderBy("createdAt", com.google.firebase.firestore.Query.Direction.DESCENDING)
                .limit(1)
                .get().awaitWithTimeout()
            val notice = if (!result.isEmpty) {
                val doc = result.documents[0]
                val timestamp = doc.getTimestamp("createdAt")
                val formattedDate = timestamp?.toDate()?.let { formatter.format(it) } ?: ""
                Notice(
                    id = doc.id,
                    iconEmoji = "📢",
                    title = doc.getString("title") ?: "",
                    date = formattedDate,
                    content = doc.getString("content") ?: ""
                )
            } else {
                null
            }
            RepositoryResult.Success(notice)
        } catch (e: Exception) {
            RepositoryResult.Error(repositoryFailure("최신 공지 조회", e))
        }
    }
}
