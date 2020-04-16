from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views import generic
from django.utils import timezone
from .models import Quiz, Category, Question, Answer, Feedback
from django.contrib.sessions.backends.db import SessionStore

# Built following alongside Django Software Foundation's Writing your first Django app Tutorial
# https://docs.djangoproject.com/en/3.0/intro/tutorial01/

class IndexView(generic.ListView):
    template_name = 'quizzes/index.html'
    context_object_name = 'latest_quiz_list'

    def get_queryset(self):
        """Return the last five published quizzes"""
        return Quiz.objects.filter(pub_date__lte=timezone.now()).order_by('-pub_date')[:5]


class QuizDetailView(generic.DetailView):
    model = Quiz
    template_name = 'quizzes/quiz_detail.html'

    def get_queryset(self):
        """Return the last five published quizzes"""
        return Quiz.objects.filter(pub_date__lte=timezone.now())


class CategoryDetailView(generic.DetailView):
    model = Category
    template_name = 'quizzes/category_detail.html'


class QuestionDetailView(generic.DetailView):
    model = Question
    template_name = 'quizzes/question_detail.html'


class FeedbackView(generic.DetailView):
    model = Feedback
    SessionStore().clear_expired()
    template_name = 'quizzes/feedback.html'


    # NOT WORKING: Function to normalize and sort scores
    @property
    def norm_sort_scores(self):
        # Get vars
        quiz = get_object_or_404(Quiz, pk=self.pk_url_kwarg())
        # Normalize the scores to 0-10 range
        old_min = 0
        new_min = 0
        new_max = 10

        # Make a blank list for the normalized scores
        norm_scores_list = []
        # Since multiple categories, iterate through quiz and normalize scores
        for i in range(len(quiz.category_set.all())):
            # Get current category
            category = get_object_or_404(Category, pk=i)

            # Get other values to calculate normalized values
            old_max = len(category.question_set.all())
            old_score = category.score

            # Normalize
            new_score = ((new_max - new_min) / (old_max - old_min)) * (old_score - old_max) + new_max

            #U pdate list and Category score
            norm_scores_list.append(new_score)
            Category.objects.filter(id=i).update(score=new_score) # Update category scores

        # Sort and reverse, scores so we can return the bottom 2 scores
        norm_scores_list.sort(reverse=True)
        return norm_scores_list[:1]


def new_quiz(request, quiz_id, category_id):
    """Function to create a new session, resets category score and answer selected booleans to default"""
    SessionStore().create()

    # Reset the category score values to zero
    Category.objects.values_list('score').update(score=0)
    # Reset the answer values to false
    Answer.objects.values_list('answer_selected').update(answer_selected=False)

    return HttpResponseRedirect(reverse('quizzes:take_quiz', args=(quiz_id, category_id, 1)))  # take_quiz(request, quiz, question)


def take_quiz(request, quiz_id, category_id, question_id):
    """View Function that is responsible for rendering the question pages of the quiz"""
    # Get vars
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    question = get_object_or_404(Question, pk=question_id)
    return render(request, 'quizzes/take_quiz.html', {'quiz': quiz_id, 'category': category_id, 'question': question})


def select_answer(request, quiz_id, category_id, question_id):
    """Function to submit an answer and continue paging through the quiz. If no more questions, redirects to feedback"""

    # Get vars
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    category = get_object_or_404(Category, pk=category_id)
    question = get_object_or_404(Question, pk=question_id)
    last_question = len(quiz.question_set.all())

    try: # Check if an answer is selected
        selected_answer = question.answer_set.get(pk=request.POST['answer'])
    except (KeyError, Answer.DoesNotExist):
        # Redisplay the question if answer is not selected
        return render(request, 'quizzes/take_quiz.html', {
            'quiz': quiz,
            'question': question,
            'error_message': "You didn't select an answer.",
        })
    else:
        # Update parameters based on selection
        selected_answer.answer_selected = True
        category_score = category.score
        answer_score = selected_answer.answer_weight
        Category.objects.filter(id=category_id).update(score=category_score + answer_score)
        selected_answer.save()

        # Continue with quiz, or redirect to feedback when on last question
        if question_id == last_question:  # Finished Answering Questions for quiz, redirect to feedback
            return redirect('quizzes:feedback', quiz_id)
        else:
            return HttpResponseRedirect(reverse('quizzes:take_quiz', args=(quiz_id, category_id, question_id + 1)))