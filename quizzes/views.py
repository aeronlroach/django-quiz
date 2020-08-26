import csv, io, datetime
from django.contrib.auth.decorators import permission_required
from django.views.decorators.cache import cache_page
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.views import generic
from django.utils import timezone
from .models import Quiz, Category, Question, Answer, Feedback, UserResponse
from .render import Render
from django.core.exceptions import ObjectDoesNotExist
from random import choice


# Built following alongside Django Software Foundation's Writing your first Django app Tutorial
# https://docs.djangoproject.com/en/3.0/intro/tutorial01/

class IndexView(generic.ListView):
    template_name = 'quizzes/index.html'
    context_object_name = 'latest_quiz_list'

    def get_queryset(self):
        """Return the last five published, active quizzes"""
        return Quiz.objects.filter(active_quiz=True).order_by('-pub_date')[:5]


class QuizDetailView(generic.DetailView):
    model = Quiz
    template_name = 'quizzes/quiz_detail.html'

    def get_queryset(self):
        """Return the active quizzes"""
        return Quiz.objects.filter(active_quiz=True).order_by('-pub_date')


@permission_required('admin.can_add_log_entry')
def quiz_upload(request):
    """
    This is a function that lets the superuser upload a CSV to create or edit a quiz.
    """
    template = "quizzes/quiz_upload.html"
    prompt = {
        'headerorder': 'Order of the CSV header should be Quiz name, pub_date, description',
        'order': 'Order for rest of CSV should be Quiz name, '
                 'category_name, question_text, answer_text, answer_weight, feedback_text',
        'feedbacknote': 'If you do not plan on including feedback for an answer put No Feedback for feedback_text',
    }
    error_msg = 'This is csv file is not formatted correctly, please check the file and try again'

    if request.method == 'GET':
        return render(request, template, prompt)

    csv_file = request.FILES['file']

    # Check if the submitted file is .csv format
    if not csv_file.name.endswith('.csv'):
        messages.error(request, template, 'This is not a csv file')

    quiz_contents = csv_file.read().decode('UTF-8')
    io_string = io.StringIO(quiz_contents)

    # Create/Update Quiz using first row of csv, check for proper format
    csv_header = next(csv.reader(io_string, delimiter=',', quotechar="|"))
    try:
        # Added an extra layer of error catching, this will try to enter the time in the full datetime format
        # if not in datetime %Y-%m-%d %H:%M:%S.%f', then it will just try the date given
        try:
            quiz_obj, quiz_created = Quiz.objects.update_or_create(
                name=csv_header[0],
                pub_date=datetime.datetime.strptime(csv_header[1], '%Y-%m-%d %H:%M:%S.%f'),
                description=csv_header[2],
                active_quiz=True,
            )
        except ValueError:
            quiz_obj, quiz_created = Quiz.objects.update_or_create(
                name=csv_header[0],
                pub_date=csv_header[1],
                description=csv_header[2],
                active_quiz=True,
            )

    # If there is an Index Error, the created object is deleted and the page is reloaded with the error message
    except IndexError:
        try:
            Quiz.objects.filter(quiz_name=quiz_obj.quiz_name).delete()
        except ObjectDoesNotExist:
            pass
        render(request, template, prompt)
        messages.error(request, error_msg)

    # Creating sets to check old upload vs new upload
    if quiz_created is False:
        categories = quiz_obj.category_set.all()
        questions = quiz_obj.question_set.all()
        answers = quiz_obj.answer_set.all()
        feedback_set = quiz_obj.feedback_set.all()
        quiz_c_old = set(c.category_name for c in categories)
        quiz_c_new = set()
        quiz_q_old = set(q.question_text for q in questions)
        quiz_q_new = set()
        quiz_a_old = set((a.answer_text, a.answer_weight) for a in answers)
        quiz_a_new = set()
        quiz_f_old = set(f.feedback_text for f in feedback_set)
        quiz_f_new = set()

    # Now create the rest of the Quiz elements, u
    for row in csv.reader(io_string, delimiter=',', quotechar="|"):
        try:
            category_obj, created = Category.objects.update_or_create(
                parent_quiz=quiz_obj,
                category_name=row[1],
                order=0,
                description='',
                score=0
            )
            question_obj, created = Question.objects.update_or_create(
                parent_quiz=quiz_obj,
                parent_category=category_obj,
                question_text=row[2]
            )
            answer_obj, created = Answer.objects.update_or_create(
                parent_quiz=quiz_obj,
                parent_category=category_obj,
                parent_question=question_obj,
                answer_text=row[3],
                answer_selected=False,
                answer_weight=row[4]
            )
            feedback_obj, created = Feedback.objects.update_or_create(
                parent_quiz=quiz_obj,
                parent_category=category_obj,
                parent_question=question_obj,
                parent_answer=answer_obj,
                feedback_type='',
                feedback_text=row[5]
            )
            if quiz_created is False:
                quiz_c_new.add(category_obj.category_name)
                quiz_q_new.add(question_obj.question_text)
                quiz_a_new.add((answer_obj.answer_text, answer_obj.answer_weight))
                quiz_f_new.add(feedback_obj.feedback_text)

        # If there is an error in the format of the CSV, Error raised.
        # Anything that was created relating to the quiz is deleted and the page is reloaded with an error message
        except IndexError or ValueError:
            try:
                Feedback.objects.filter(parent_quiz=quiz_obj).delete()
                Answer.objects.filter(parent_quiz=quiz_obj).delete()
                Question.objects.filter(parent_quiz=quiz_obj).delete()
                Category.objects.filter(parent_quiz=quiz_obj).delete()
                Quiz.objects.filter(quiz_name=quiz_obj.quiz_name).delete()
            except ObjectDoesNotExist:
                pass
            render(request, template, prompt)
            messages.error(request, error_msg)

    # Checking what was removed between uploads
    if quiz_created is False:
        removed_c = quiz_c_old.difference(quiz_c_new)
        removed_q = quiz_q_old.difference(quiz_q_new)
        removed_a = quiz_a_old.difference(quiz_a_new)
        removed_f = quiz_f_old.difference(quiz_f_new)

        # Removing anything that was not in the new csv
        if removed_c:
            for i in removed_c:
                category = Category.objects.filter(parent_quiz=quiz_obj, category_name=str(i)).get()
                Feedback.objects.filter(parent_quiz=quiz_obj, parent_category=category).delete()
                Answer.objects.filter(parent_quiz=quiz_obj, parent_category=category).delete()
                Question.objects.filter(parent_quiz=quiz_obj, parent_category=category).delete()
                Category.objects.filter(parent_quiz=quiz_obj, category_name=str(i)).delete()
        if removed_q:
            for i in removed_q:
                try:
                    question = Question.objects.filter(parent_quiz=quiz_obj, question_text=str(i)).get()
                    Feedback.objects.filter(parent_quiz=quiz_obj, parent_question=question).delete()
                    Answer.objects.filter(parent_quiz=quiz_obj, parent_question=question).delete()
                    Question.objects.filter(parent_quiz=quiz_obj, question_text=str(i)).delete()
                except ObjectDoesNotExist:
                    pass
        if removed_a:
            for i in removed_a:
                try:
                    answer = Answer.objects.filter(parent_quiz=quiz_obj, answer_text=str(i[0]), answer_weight=i[1]).get()
                    Feedback.objects.filter(parent_quiz=quiz_obj, parent_answer=answer).delete()
                    Answer.objects.filter(parent_quiz=quiz_obj, answer_text=str(i[0]), answer_weight=i[1]).delete()
                except ObjectDoesNotExist:
                    pass
        if removed_f:
            for i in removed_f:
                try:
                    Feedback.objects.filter(parent_quiz=quiz_obj, feedback_text=str(i)).delete()
                except ObjectDoesNotExist:
                    pass

    context = {
        "success": 'The quiz was uploaded successfully',
        'headerorder': 'Order of the CSV header should be Quiz name, pub_date, description',
        'order': 'Order for rest of CSV should be Quiz name, '
                 'category_name, question_text, answer_text, answer_weight, feedback_text',
        'feedbacknote': 'If you do not plan on including feedback for an answer put No Feedback for feedback_text',
    }

    return render(request, template, context)


def generate_new_id(quiz_id):
    range_low = quiz_id*1000
    range_high = range_low + 999
    ids = set(range(range_low, range_high))
    used_ids = set(UserResponse.objects.values_list('response_id', flat=True))
    return choice(list(ids - used_ids))


def create_user_response(quiz_id, *args):
    """
    Function to create a new response database entry,
    response_id is left default to be produced with the
    UserResponse class's generate_new_id function

    Returns the UserResponse object response_id
    """
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    if args:
        response_obj, created = UserResponse.objects.update_or_create(
            parent_quiz=quiz,
            response_id=args[0]['user_id'],
            defaults=dict(response_data=args[0]['quiz_dictionary']),
        )
        return response_obj.response_id
    else:
        response_obj, created = UserResponse.objects.update_or_create(
            parent_quiz=quiz,
            response_id=generate_new_id(quiz_id),
        )

        return response_obj.response_id


def save_user_feedback(request, user_id):
    user = UserResponse.objects.filter(response_id=user_id).get()
    quiz = user.parent_quiz

    # Get session variables for rendering
    quiz_data = request.session[quiz.session_quiz_data()]
    feed_dict = request.session[quiz.session_feedback()]
    norm_scores_dict = request.session[quiz.session_norm_data()]

    # Updating session's UserResponse to
    create_user_response(quiz.id, {'user_id': user_id, 'quiz_dictionary': {'quiz_data': quiz_data,
                                                                           'quiz_norm_scores': norm_scores_dict,
                                                                           'feedback_data': feed_dict}})


def start_new_quiz(request, quiz_id, category_id):
    """
    Function to create a new quiz session variables when "Take Quiz" button is selected.
    """
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    quiz_id = quiz.id
    categories = quiz.get_quiz_categories()
    category_id = quiz.category_set.first().id
    questions = quiz.get_quiz_questions()
    question_id = quiz.question_set.first().id
    question_list = [q.id for q in questions]

    # Set session variables for quiz
    request.session.flush()
    request.session[quiz.session_question_list()] = question_list

    # Quiz data dictionary formatted:
    # {category_name: {question_name : answer_selected} }
    data = {}
    for i in range(len(categories)):
        innerdict = {}
        category = categories[i]
        cat_questions = category.question_set.all()
        for j in range(len(cat_questions)):
            question_list_item = cat_questions[j]
            innerdict.update({question_list_item.question_text: None})
        data.update({category.category_name: innerdict})
    request.session[quiz.session_quiz_data()] = data

    category_score_data = {categories[i].category_name: None for i in range(len(categories))}
    request.session[quiz.session_cat_data()] = category_score_data
    request.session[quiz.session_norm_data()] = category_score_data

    # # Create new new user response
    user_id = create_user_response(quiz_id)
    request.session[quiz.session_response_id()] = user_id

    return HttpResponseRedirect(
        reverse('quizzes:take_quiz', args=(quiz.id, category_id, question_id)))


def take_quiz(request, quiz_id, category_id, question_id):
    """
    View Function that is responsible for rendering the question pages of the quiz
    """
    # Get vars
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    question_id = Question.objects.get_subclass(id=question_id)
    return render(request, 'quizzes/take_quiz.html',
                  {'quiz': quiz.id, 'category': category_id, 'question': question_id})


def select_answer(request, quiz_id, category_id, question_id):
    """
    Function to submit an answer and continue paging through the quiz.
    If no more questions, redirects to feedback
    """

    # Get vars
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    category = get_object_or_404(Category, pk=category_id)
    category_name = category.category_name
    question = get_object_or_404(Question, pk=question_id)
    question_text = question.question_text
    last_question = request.session[quiz.session_question_list()][-1]

    try:  # Check if an answer is selected
        selected_answer = question.answer_set.get(pk=request.POST['answer'])
    except (KeyError, Answer.DoesNotExist):
        # Redisplay the question if answer is not selected
        return render(request, 'quizzes/take_quiz.html', {
            'quiz': quiz,
            'question': question,
            'error_message': "You didn't select an answer.",
        })
    else:
        # Update session variables based on selection
        question_data = request.session[quiz.session_quiz_data()]
        question_data[str(category_name)][str(question_text)] = selected_answer.answer_text
        category_score = request.session[quiz.session_cat_data()]
        answer_score = selected_answer.answer_weight
        if category_score[str(category_name)] is None:
            category_score[str(category_name)] = answer_score
        elif category_score[str(category_name)] is not None:
            category_score[str(category_name)] = category_score[str(category_name)] + answer_score

        # Save session variables
        request.session[quiz.session_cat_data()] = category_score
        request.session[quiz.session_quiz_data()] = question_data

        # Continue with quiz, or redirect to feedback when on last question
        if question_id == last_question:  # Finished Answering Questions for quiz, redirect to feedback
            normalize_scores(request, quiz_id)
            get_session_feedback(request, quiz_id)
            user_id = request.session[quiz.session_response_id()]
            save_user_feedback(request, user_id)
            return HttpResponseRedirect(reverse('quizzes:feedback', args=(user_id,)))
        else:
            return HttpResponseRedirect(reverse('quizzes:take_quiz', args=(quiz_id, category_id, question_id + 1)))


def get_session_data(request, quiz_id):
    """
    Helper function that takes the request and quiz_id as arguments and returns
    useful variables
    """
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    quiz_data = request.session[quiz.session_quiz_data()]
    category_score_dict = request.session[quiz.session_cat_data()]
    norm_score_dict = request.session[quiz.session_norm_data()]
    questions_list = request.session[quiz.session_question_list()]
    return quiz, quiz_data, category_score_dict, norm_score_dict, questions_list


def normalize_scores(request, quiz_id):
    """
    This is a function to normalize the category scores to a scale of 0-10. I have assumed that the max weight
    for each question is 1, and the min is 0. I will need to update this to adapt to the varying max and min
    weights from each question, as well as adapting to admin defined score ranges.

    Dictionary format: {category_name : normalized score}
    """
    quiz, quiz_data, category_score_dict, norm_score_dict, questions_list = get_session_data(request, quiz_id)
    categories = quiz.get_quiz_categories()

    # Creating a list of the max score for each section, needed to normalize to a score range of 0 - 10
    old_max_list = []
    for i in range(len(category_score_dict)):
        category = categories[i]
        old_max_list.append(len(quiz_data[str(category.category_name)]))

    # Normalizing the old scores and populating the session variable session_norm_data, round to 2 decimal places
    norm_score_list = [
        round((
                (10 / (old_max_list[i] - 0)) *
                (category_score_dict[str(categories[i].category_name)] - old_max_list[i]) + 10
            ), 2
        )
        for i in range(len(category_score_dict))
    ]

    for i in range(len(category_score_dict)):
        category = categories[i]
        if norm_score_list[i] is not None:
            norm_score_dict[str(category.category_name)] = norm_score_list[i]
    request.session[quiz.session_norm_data()] = norm_score_dict
    return request.session[quiz.session_norm_data()]


def get_session_feedback(request, quiz_id):
    """
    Function to create a dictionary of feedback for the session
    Returns a dictionary formatted:
    {category_name: {question_text : feedback_text} }
    """
    quiz, quiz_data, category_score_dict, norm_score_dict, questions_list = get_session_data(request, quiz_id)
    categories = quiz.get_quiz_categories()

    # Creating the feedback dictionary to populate the session variable session_feedback
    feedback_set = {}
    for i in range(len(categories)):
        innerdict = {}
        category = categories[i]
        category_name = category.category_name
        cat_questions = category.question_set.all()
        for j in range(len(cat_questions)):
            question = cat_questions[j]
            question = Question.objects.filter(id=question.id).get()
            question_text = question.question_text
            answer_text = quiz_data[str(category_name)][str(question_text)]
            if answer_text is not None:
                answer = Answer.objects.filter(parent_quiz=quiz, answer_text=answer_text).get()
                check_feedback = answer.get_quiz_feedback().get()
                if answer.answer_weight < 1:
                    answer_feedback = check_feedback.feedback_text
                    innerdict.update({question_text: answer_feedback})
                if answer.answer_weight == 1:
                    answer_feedback = check_feedback.feedback_text
                    if answer_feedback == "No Feedback":
                        answer_feedback = None
                    innerdict.update({question_text: answer_feedback})
        feedback_set.update({category_name: innerdict})
    request.session[quiz.session_feedback()] = feedback_set
    return request.session[quiz.session_feedback()]


@cache_page(60 * 15)
def feedback(request, user_id):
    """
    This is the feedback page that users will see once they are done with a quiz.
    This page is cached and uses the UserResponse Model to show a limited amount of feedback
    """
    request.session.set_expiry(1)
    user = UserResponse.objects.filter(response_id=user_id).get()
    quiz = user.parent_quiz

    # Get session variables for rendering
    quiz_data = user.response_data['quiz_data']
    norm_scores_dict = user.response_data['quiz_norm_scores']
    feed_dict = user.response_data['feedback_data']
    number_of_sections = 2
    sorted_scores_limited = {k: v
                             for k, v in sorted(norm_scores_dict.items(), key=lambda item: item[1])[:number_of_sections]
                             }

    return render(request, 'quizzes/feedback.html', {
        'quiz': quiz,
        'feed_dict': feed_dict,
        'norm_scores': norm_scores_dict,
        'sorted_scores_limit': sorted_scores_limited,
        'user_id': user_id
    })


@cache_page(60 * 60)
def get_feedback_pdf(request, user_id):
    """
    This is a feedback page that is rendered as a pdf. Users will be able to access this from the feedback page.
    This page is cached and uses the response_data object of the UserResponse Model.
    """
    today = timezone.now()
    user = UserResponse.objects.filter(response_id=user_id).get()
    quiz = user.parent_quiz

    # Get session variables for rendering
    quiz_data = user.response_data['quiz_data']
    norm_scores_dict = user.response_data['quiz_norm_scores']
    feed_dict = user.response_data['feedback_data']
    context = {
        'user_id': user_id,
        'today': today,
        'quiz': quiz,
        'quiz_data': quiz_data,
        'feed_dict': feed_dict,
        'norm_scores': norm_scores_dict,
    }
    return Render.render('quizzes/get_feedback_pdf.html', context)
