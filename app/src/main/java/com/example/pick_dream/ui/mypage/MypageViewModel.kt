package com.example.pick_dream.ui.mypage

import android.util.Log
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import com.example.pick_dream.model.User
import com.example.pick_dream.repository.UserRepository

/**
 * MypageFragment의 UI 상태를 관리하는 ViewModel.
 * 사용자 정보 조회는 Firestore를 통해 수행합니다.
 */
class MyPageViewModel : ViewModel() {

    private val _userData = MutableLiveData<User?>()
    val userData: LiveData<User?> get() = _userData

    fun loadUserData() {
        UserRepository.getCurrentUser { user ->
                if (user != null) {
                    _userData.value = user
                } else {
                    Log.w("MyPageViewModel", "User document is empty or malformed.")
                }
        }
    }
}
