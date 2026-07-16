package com.example.pick_dream.ui.home

import android.content.Context
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import com.example.pick_dream.model.Reservation
import com.example.pick_dream.repository.RepositoryResult

/**
 * HomeFragment의 UI 상태를 관리하는 ViewModel.
 * Firestore, SharedPreferences 등 데이터 접근은 HomeRepository에 위임합니다.
 */
class HomeViewModel : ViewModel() {

    private val _reservation = MutableLiveData<Reservation?>()
    val reservation: LiveData<Reservation?> = _reservation

    private val _isLoading = MutableLiveData<Boolean>(false)
    val isLoading: LiveData<Boolean> = _isLoading

    private val _message = MutableLiveData<String>()
    val message: LiveData<String> = _message

    /**
     * 현재 진행 중이거나 가장 임박한 예약 정보를 로드합니다.
     */
    fun loadReservation() {
        _isLoading.value = true
        HomeRepository.fetchActiveOrUpcomingReservation { result ->
            when (result) {
                is RepositoryResult.Success -> _reservation.postValue(result.data)
                is RepositoryResult.Error -> _message.postValue(result.failure.userMessage)
            }
            _isLoading.postValue(false)
        }
    }

    /**
     * 예약 정보를 SharedPreferences에 저장합니다.
     */
    fun saveReservationPrefs(context: Context, endTimeMillis: Long, roomId: String) {
        HomeRepository.saveReservationPrefs(context, endTimeMillis, roomId)
    }
}
