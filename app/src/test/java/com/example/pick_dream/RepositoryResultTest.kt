package com.example.pick_dream

import com.example.pick_dream.repository.RepositoryErrorKind
import com.example.pick_dream.repository.RepositoryFailure
import com.example.pick_dream.repository.RepositoryResult
import com.example.pick_dream.repository.authenticationFailure
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RepositoryResultTest {

    @Test
    fun authenticationFailure_hasActionableMessage() {
        val failure = authenticationFailure("예약 생성")

        assertEquals(RepositoryErrorKind.AUTHENTICATION, failure.kind)
        assertEquals("예약 생성", failure.operation)
        assertEquals("로그인이 필요합니다.", failure.userMessage)
    }

    @Test
    fun everyFailureKind_hasUserMessage() {
        RepositoryErrorKind.entries.forEach { kind ->
            val failure = RepositoryFailure(kind, "테스트")
            assertTrue(failure.userMessage.isNotBlank())
        }
    }

    @Test
    fun success_preservesEmptyCollectionAsValidData() {
        val result: RepositoryResult<List<String>> = RepositoryResult.Success(emptyList())

        assertTrue(result is RepositoryResult.Success)
        assertEquals(emptyList<String>(), (result as RepositoryResult.Success).data)
    }
}
