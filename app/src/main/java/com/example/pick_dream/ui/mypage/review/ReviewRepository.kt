package com.example.pick_dream.ui.mypage.review

import com.example.pick_dream.model.Review
import com.example.pick_dream.repository.UserRepository
import com.example.pick_dream.repository.NetworkStatus
import com.example.pick_dream.repository.RepositoryResult
import com.example.pick_dream.repository.authenticationFailure
import com.example.pick_dream.repository.awaitWithTimeout
import com.example.pick_dream.repository.dataFailure
import com.example.pick_dream.repository.networkFailure
import com.example.pick_dream.repository.repositoryFailure
import com.example.pick_dream.util.RoomIdUtils
import com.google.firebase.firestore.TransactionOptions
import com.google.firebase.firestore.ktx.firestore
import com.google.firebase.ktx.Firebase

object ReviewRepository {
    private val db = Firebase.firestore
    private val transactionOptions = TransactionOptions.Builder()
        .setMaxAttempts(1)
        .build()

    /**
     * 특정 유저(학번)가 작성한 리뷰 목록을 최신순으로 가져옵니다.
     */
    suspend fun getReviewsByUser(studentId: String): RepositoryResult<List<Review>> {
        return try {
            val snapshot = db.collection("Reviews")
                .whereEqualTo("userID", studentId)
                .get()
                .awaitWithTimeout()

            RepositoryResult.Success(
                snapshot.documents
                    .filterNot { it.metadata.hasPendingWrites() }
                    .mapNotNull { it.toObject(Review::class.java) }
                    .sortedByDescending { it.createdAt }
            )
        } catch (e: Exception) {
            RepositoryResult.Error(repositoryFailure("내 리뷰 조회", e))
        }
    }

    /**
     * 모든 리뷰 목록을 가져옵니다. (지도 평균 별점 계산용)
     */
    suspend fun getAllReviews(): RepositoryResult<List<Review>> {
        return try {
            val snapshot = db.collection("Reviews").get().awaitWithTimeout()
            RepositoryResult.Success(
                snapshot.documents
                    .filterNot { it.metadata.hasPendingWrites() }
                    .mapNotNull { it.toObject(Review::class.java) }
            )
        } catch (e: Exception) {
            RepositoryResult.Error(repositoryFailure("전체 리뷰 조회", e))
        }
    }

    /**
     * 새로운 리뷰를 Firestore에 추가합니다.
     */
    suspend fun addReview(review: Review): RepositoryResult<Unit> {
        return try {
            val ownerUid = UserRepository.getCurrentUid()
                ?: return RepositoryResult.Error(authenticationFailure("리뷰 생성"))
            if (!NetworkStatus.hasValidatedInternet()) {
                return RepositoryResult.Error(networkFailure("리뷰 생성"))
            }
            if (!RoomIdUtils.isCanonicalRoomId(review.roomID)) {
                return RepositoryResult.Error(dataFailure("리뷰 생성"))
            }
            val document = db.collection("Reviews").document()
            db.runTransaction(transactionOptions) { transaction ->
                transaction.set(document, review.copy(ownerUid = ownerUid))
                Unit
            }.awaitWithTimeout()
            RepositoryResult.Success(Unit)
        } catch (e: Exception) {
            RepositoryResult.Error(repositoryFailure("리뷰 생성", e))
        }
    }
}
