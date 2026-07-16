package com.example.pick_dream.ui.mypage.review

import android.util.Log
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.pick_dream.model.Review
import com.example.pick_dream.repository.RepositoryResult
import com.example.pick_dream.repository.UserRepository
import com.example.pick_dream.repository.repositoryFailure
import kotlinx.coroutines.launch

class ReviewViewModel : ViewModel() {

    private val _reviews = MutableLiveData<List<Review>>()
    val reviews: LiveData<List<Review>> get() = _reviews

    private val _isLoading = MutableLiveData<Boolean>()
    val isLoading: LiveData<Boolean> get() = _isLoading

    private val _message = MutableLiveData<String>()
    val message: LiveData<String> get() = _message

    fun loadReviews() {
        _isLoading.value = true

        viewModelScope.launch {
            try {
                val studentId = UserRepository.getCurrentStudentId()

                if (studentId.isNullOrBlank()) {
                    _message.value = "학번 정보를 찾을 수 없습니다."
                    _reviews.value = emptyList()
                    _isLoading.value = false
                    return@launch
                }

                // 학번을 기준으로 리뷰 목록 조회
                when (val result = ReviewRepository.getReviewsByUser(studentId)) {
                    is RepositoryResult.Success -> _reviews.value = result.data
                    is RepositoryResult.Error -> _message.value = result.failure.userMessage
                }

            } catch (e: Exception) {
                Log.e("ReviewViewModel", "리뷰 로딩 실패", e)
                _message.value = repositoryFailure("리뷰 목록 조회", e).userMessage
            } finally {
                _isLoading.value = false
            }
        }
    }
}
